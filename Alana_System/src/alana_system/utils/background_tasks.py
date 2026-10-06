import asyncio
import logging
import uuid
import time
import inspect
from typing import Callable, Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("alana.utils.tasks")

class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"

@dataclass
class TaskMetadata:
    id: str
    name: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    retries: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    namespace: str = "global"

class BackgroundTaskManager:
    """
    Gerenciador de Tarefas em Background Industrial.
    Oferece resiliência (retries), observabilidade e controle de ciclo de vida.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BackgroundTaskManager, cls).__new__(cls)
            cls._instance.tasks: Dict[str, TaskMetadata] = {}
            cls._instance._lock = asyncio.Lock()
            logger.info("⚙️ BackgroundTaskManager Inicializado | Resiliência Ativada")
        return cls._instance

    def run_task(
        self, 
        coro_func: Callable[..., Any], 
        *args, 
        name: str = None, 
        namespace: str = "global", 
        max_retries: int = 3,
        **kwargs
    ) -> str:
        """
        Agenda uma tarefa para execução em background com monitoramento.
        """
        task_id = str(uuid.uuid4())
        task_name = name or coro_func.__name__
        try:
            signature = inspect.signature(coro_func)
            bound = signature.bind_partial(*args, **kwargs)
            if "namespace" in signature.parameters and "namespace" not in bound.arguments:
                kwargs["namespace"] = namespace
        except (TypeError, ValueError):
            logger.warning("Não foi possível inferir o namespace para a tarefa %s", task_name)
        
        # Captura o contexto do log atual (Trace ID)
        from alana_system.utils.logging_context import get_trace_id
        current_trace_id = get_trace_id()

        meta = TaskMetadata(
            id=task_id,
            name=task_name,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            max_retries=max_retries,
            namespace=namespace
        )
        
        self.tasks[task_id] = meta
        
        # Inicia a execução assíncrona preservando o Trace ID
        asyncio.create_task(self._execute_with_retry(task_id, current_trace_id, coro_func, *args, **kwargs))
        
        logger.info(f"🚀 Tarefa agendada: {task_name} [{task_id}] no namespace '{namespace}'")
        return task_id

    async def _execute_with_retry(self, task_id: str, trace_id: str, coro_func: Callable, *args, **kwargs):
        # Restaura o Trace ID para o contexto desta thread asincrona
        from alana_system.utils.logging_context import set_trace_id
        set_trace_id(trace_id)
        
        meta = self.tasks[task_id]
        meta.status = TaskStatus.RUNNING
        meta.started_at = time.time()
        
        attempt = 0
        while attempt <= meta.max_retries:
            try:
                # Executa a corrotina
                await coro_func(*args, **kwargs)
                
                # Sucesso
                meta.status = TaskStatus.COMPLETED
                meta.finished_at = time.time()
                logger.info(f"✅ Tarefa concluída: {meta.name} [{task_id}]")
                return
                
            except Exception as e:
                attempt += 1
                meta.retries = attempt
                meta.error = str(e)
                
                if attempt <= meta.max_retries:
                    meta.status = TaskStatus.RETRYING
                    # Backoff exponencial simples: 1s, 2s, 4s...
                    wait_time = 2 ** (attempt - 1)
                    logger.warning(f"⚠️ Falha na tarefa {meta.name} [{task_id}]: {e}. Retentando em {wait_time}s (Tentativa {attempt}/{meta.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    meta.status = TaskStatus.FAILED
                    meta.finished_at = time.time()
                    logger.error(f"❌ Tarefa FALHOU após {meta.max_retries} tentativas: {meta.name} [{task_id}] | Erro: {e}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retorna o estado detalhado de uma tarefa."""
        meta = self.tasks.get(task_id)
        if not meta:
            return None
        return {
            "id": meta.id,
            "name": meta.name,
            "status": meta.status.value,
            "retries": meta.retries,
            "error": meta.error,
            "duration": (meta.finished_at or time.time()) - (meta.started_at or time.time())
        }

    def list_active_tasks(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista todas as tarefas em execução ou pendentes."""
        return [
            self.get_task_status(tid) 
            for tid, m in self.tasks.items() 
            if m.status in [TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.RETRYING]
            and (namespace is None or m.namespace == namespace)
        ]

    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """Remove registros de tarefas antigas para economizar memória."""
        now = time.time()
        to_remove = [
            tid for tid, m in self.tasks.items() 
            if m.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] 
            and (now - (m.finished_at or 0)) > max_age_seconds
        ]
        for tid in to_remove:
            del self.tasks[tid]
        if to_remove:
            logger.debug(f"🧹 Limpeza de tarefas: {len(to_remove)} registros removidos.")

# Instância Global Singleton
task_manager = BackgroundTaskManager()
