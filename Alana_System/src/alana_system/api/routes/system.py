import os
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from alana_system.utils.background_tasks import task_manager

router = APIRouter(prefix="/system", tags=["System Observability"])

@router.get("/tasks")
async def list_background_tasks(namespace: str = None):
    """
    Lista todas as tarefas de background ativas para observabilidade industrial.
    """
    return {
        "active_tasks": task_manager.list_active_tasks(namespace=namespace),
        "total_tracked": len(task_manager.tasks)
    }

@router.get("/tasks/{task_id}")
async def get_task_details(task_id: str):
    """
    Retorna os detalhes de uma tarefa específica.
    """
    status = task_manager.get_task_status(task_id)
    if not status:
        return {"error": "Tarefa nao encontrada"}
    return status

@router.post("/tasks/cleanup")
async def cleanup_tasks(max_age: int = 3600):
    """
    Remove registros de tarefas antigas.
    """
    task_manager.cleanup_old_tasks(max_age)
    return {"status": "success"}

@router.get("/artifacts")
async def list_artifacts():
    """
    Lista os artefatos gerados (PDFs, imagens, relatórios) na pasta output.
    """
    output_dir = "data/artifacts"
    if not os.path.exists(output_dir):
        return {"artifacts": []}
    
    files = []
    for f in os.listdir(output_dir):
        path = os.path.join(output_dir, f)
        if os.path.isfile(path):
            files.append({
                "name": f,
                "size": os.path.getsize(path),
                "mtime": os.path.getmtime(path),
                "url": f"/data/artifacts/{f}"
            })
    
    # Ordena pelos mais recentes
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"artifacts": files}

@router.get("/stream")
async def system_stream(request: Request, namespace: str = "global"):
    """
    Server-Sent Events para atualização em tempo real de logs, tasks, artifacts e jobs.
    """
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            
            try:
                # 1. Tasks
                tasks_data = {
                    "tasks": task_manager.list_active_tasks(namespace=namespace),
                    "total_tracked": len(task_manager.tasks)
                }
                yield f"event: tasks\ndata: {json.dumps(tasks_data)}\n\n"
                
                # 2. Artifacts
                output_dir = "data/artifacts"
                files = []
                if os.path.exists(output_dir):
                    for f in os.listdir(output_dir):
                        path = os.path.join(output_dir, f)
                        if os.path.isfile(path):
                            files.append({
                                "name": f,
                                "size": os.path.getsize(path),
                                "mtime": os.path.getmtime(path),
                                "url": f"/data/artifacts/{f}"
                            })
                    files.sort(key=lambda x: x["mtime"], reverse=True)
                yield f"event: artifacts\ndata: {json.dumps({'artifacts': files})}\n\n"
                
                # 3. Ingestion Jobs
                graph_store = getattr(request.app.state, 'graph_store', None)
                if graph_store:
                    all_jobs = graph_store.get_all_jobs()
                    jobs = [j for j in all_jobs if j.get("namespace") == namespace] if all_jobs else []
                    yield f"event: jobs\ndata: {json.dumps({'jobs': jobs})}\n\n"
                    readings = graph_store.get_recent_telemetry(namespace, limit=50)
                    yield f"event: telemetry\ndata: {json.dumps({'readings': readings})}\n\n"
                    
                # 4. Logs
                log_file = "alana.log"
                if os.path.exists(log_file):
                    with open(log_file, "r", encoding="utf-8", errors="replace") as lf:
                        lines = lf.readlines()[-50:] # last 50 lines
                        logs_str = "".join(lines).replace('\n', '<br>')
                        yield f"event: logs\ndata: {json.dumps({'logs': logs_str})}\n\n"
                
            except Exception as e:
                yield f"event: server_error\ndata: {json.dumps({'error': str(e)})}\n\n"
            
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
