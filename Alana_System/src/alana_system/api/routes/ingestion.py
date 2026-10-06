import logging
import threading
import shutil
import uuid
import re
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Query, Request
from pydantic import BaseModel
from pathlib import Path
from typing import List, Optional, Dict, Any
from alana_system.agent.tools.path_utils import namespace_workspace

from alana_system.api.dependencies import get_embedder, get_llm_engine, get_vector_store, get_graph_store
from alana_system.ingestion.manager import IngestionManager, SUPPORTED_FILE_EXTENSIONS

logger = logging.getLogger("alana.api.ingestion")
router = APIRouter(tags=["Ingestion"], prefix="/ingestion")

import asyncio
# Limite de concorrência para proteger CPU/GPU local
ingestion_semaphore = asyncio.Semaphore(2)

class ProcessPathRequest(BaseModel):
    path: str
    namespace: str = "global"

async def _background_ingestion_task(file_path: Path, namespace: str, app_state: Any, mode: str = "fast"):
    """Executa a ingestão industrial em segundo plano com controle de concorrência assíncrona."""
    async with ingestion_semaphore:
        try:
            # Utiliza a inteligência do Container Factory injetada no state para evitar locks no DB Local
            intelligence = app_state.graph_intelligence
            
            manager = IngestionManager(
                graph_store=app_state.graph_store,
                vector_store=app_state.vector_store,
                intelligence=intelligence,
                embedder=app_state.embedder
            )
            
            logger.info(f"⚙️ [Background] Processando: {file_path.name} no namespace '{namespace}' (Modo: {mode})")
            if file_path.is_dir():
                await manager.process_directory(str(file_path), namespace=namespace, mode=mode)
            else:
                await manager.process_file(str(file_path), namespace=namespace, mode=mode)
            logger.info(f"✅ [Background] Concluído: {file_path.name}")
        except Exception as e:
            logger.error(f"❌ [Background] Falha em {file_path.name}: {e}", exc_info=True)

@router.post("/upload")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    namespace: str = Query("global", description="O projeto onde o arquivo sera guardado"),
    mode: str = Query("fast", description="Modo de ingestão: 'fast' ou 'deep'")
):
    """Recebe um arquivo e agenda o processamento industrial assíncrono."""
    # Verificação preventiva: Se o semáforo estiver "cheio", avisamos o usuário.
    if ingestion_semaphore.locked():
        raise HTTPException(status_code=503, detail="Servidor ocupado processando outros arquivos. Tente novamente em instantes.")

    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", namespace):
            raise HTTPException(status_code=422, detail="Namespace inválido.")
        if mode not in {"fast", "deep"}:
            raise HTTPException(status_code=422, detail="Modo inválido.")
        filename = file.filename or ""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,119}", filename) or filename in {".", ".."}:
            raise HTTPException(status_code=422, detail="Nome de arquivo inválido.")
        if Path(filename).suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Formato não suportado. Aceitos: {', '.join(sorted(SUPPORTED_FILE_EXTENSIONS))}.")
        upload_dir = namespace_workspace(Path("data/uploads"), namespace)
        file_path = upload_dir / uuid.uuid4().hex / filename
        file_path.parent.mkdir(parents=True, exist_ok=False)
        total_bytes = 0
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > 100 * 1024 * 1024:
                    shutil.rmtree(file_path.parent, ignore_errors=True)
                    raise HTTPException(status_code=413, detail="Limite de upload: 100 MB.")
                f.write(chunk)

        # Agenda tarefa em background
        background_tasks.add_task(_background_ingestion_task, file_path, namespace, request.app.state, mode)

        return {
            "status": "processing",
            "message": f"Arquivo '{file.filename}' recebido. Processando em segundo plano no namespace '{namespace}'. Modo: {mode}",
            "namespace": namespace
        }
    except HTTPException:
        raise
    except Exception as e:
        if "file_path" in locals():
            shutil.rmtree(file_path.parent, ignore_errors=True)
        logger.error(f"❌ Erro no upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process-path")
async def process_local_path(
    request: Request,
    request_data: ProcessPathRequest,
    background_tasks: BackgroundTasks
):
    """Processa uma pasta local ja existente no servidor."""
    path = Path(request_data.path)
    try:
        upload_root = Path("data/uploads").resolve()
        path = path.resolve(strict=True)
        tenant_upload_root = namespace_workspace(upload_root, request_data.namespace)
        if not path.is_relative_to(tenant_upload_root):
            raise HTTPException(status_code=403, detail="Ingestão permitida somente na pasta de uploads do namespace.")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Caminho nao encontrado.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Caminho nao encontrado.")

    background_tasks.add_task(_background_ingestion_task, path, request_data.namespace, request.app.state)
    
    return {
        "status": "processing",
        "message": f"Processamento da pasta '{path.name}' agendado para o namespace '{request_data.namespace}'."
    }

@router.get("/jobs")
async def get_ingestion_jobs(graph_store=Depends(get_graph_store)):
    """Lista todos os trabalhos de ingestao registrados."""
    try:
        return {"jobs": graph_store.get_all_jobs()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
