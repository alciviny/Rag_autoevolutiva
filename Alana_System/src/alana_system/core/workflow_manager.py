import os
import yaml
import logging
from typing import Dict, Optional
from pathlib import Path
from .workflow import Workflow, WorkflowSession

logger = logging.getLogger("alana.core.workflow_manager")

class WorkflowManager:
    """
    Motor que gerencia a execucao de guias tecnicos assistidos.
    """
    def __init__(self, workflows_dir: str = "data/workflows", graph_store = None):
        self.workflows_dir = Path(workflows_dir)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.graph = graph_store
        self.active_sessions: Dict[str, WorkflowSession] = {} # user_id/namespace -> Session

    def load_workflow(self, name: str) -> Optional[Workflow]:
        """Carrega um manual YAML da pasta de dados."""
        file_path = self.workflows_dir / f"{name}.yaml"
        if not file_path.exists():
            logger.error(f"Workflow {name} nao encontrado em {file_path}")
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return Workflow(**data)
        except Exception as e:
            logger.error(f"Erro ao carregar workflow {name}: {e}")
            return None

    def start_session(self, namespace: str, workflow_name: str) -> Optional[str]:
        """Inicia um novo guia para o usuario."""
        wf = self.load_workflow(workflow_name)
        if not wf:
            return None
        
        session = WorkflowSession(wf)
        self.active_sessions[namespace] = session
        
        # Persistencia Industrial (P3 Auditoria)
        if self.graph:
            self.graph.save_workflow_session(namespace, workflow_name, 0)
            
        return wf.steps[0].instruction

    def save_progress(self, namespace: str):
        """Salva o estado atual da sessao no banco."""
        session = self.active_sessions.get(namespace)
        if session and self.graph:
            self.graph.save_workflow_session(namespace, session.workflow.name, session.current_step_index)

    def get_session(self, namespace: str) -> Optional[WorkflowSession]:
        """Recupera sessao da memoria ou do banco de dados (Resiliencia)."""
        if namespace not in self.active_sessions and self.graph:
            data = self.graph.get_workflow_session(namespace)
            if data:
                logger.info(f"🔄 Restaurando sessao de workflow '{data['workflow_name']}' para {namespace}")
                wf = self.load_workflow(data["workflow_name"])
                if wf:
                    session = WorkflowSession(wf)
                    session.current_step_index = data["current_step_index"]
                    if session.current_step_index >= len(wf.steps):
                        session.is_completed = True
                    self.active_sessions[namespace] = session

        return self.active_sessions.get(namespace)

    def stop_session(self, namespace: str):
        """Finaliza sessao e limpa persistencia."""
        if namespace in self.active_sessions:
            del self.active_sessions[namespace]
        if self.graph:
            self.graph.delete_workflow_session(namespace)
