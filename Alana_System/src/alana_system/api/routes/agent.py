import logging
import json
import asyncio
import contextlib
import re
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("alana.api.agent")
router = APIRouter(tags=["Agent"])


def _report_task_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error:
        logger.error("Falha em missão WebSocket", exc_info=(type(error), error, error.__traceback__))

@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    """
    Interface de comunicacao em tempo real para o Agente Autonomo (Expert Lab).
    Suporta isolamento por namespace e controle de missao.
    """
    await websocket.accept()
    from alana_system.utils.logging_context import set_trace_id, get_trace_id
    trace_id = set_trace_id()
    logger.info(f"🔌 WebSocket Agent Conectado | TraceID: {trace_id}")
    
    orchestrator = websocket.app.state.orchestrator
    current_mission_task = None

    async def stream_event(event_type: str, data: dict):
        """Envia eventos de pensamento e acao para o frontend."""
        try:
            if websocket.client_state.value == 1: # Connected
                await websocket.send_json({"type": event_type, "data": data})
        except Exception as e:
            logger.error(f"⚠️ Falha ao transmitir evento {event_type} via WebSocket: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "data": {"message": "JSON inválido."}})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "data": {"message": "A mensagem deve ser um objeto JSON."}})
                continue

            if message.get("action") == "abort":
                if current_mission_task and not current_mission_task.done():
                    current_mission_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await current_mission_task
                    current_mission_task = None
                    await websocket.send_json({"type": "mission_cancelled", "data": {"message": "Missão cancelada."}})
                else:
                    await websocket.send_json({"type": "error", "data": {"message": "Não há missão ativa para cancelar."}})
                continue
            
            # Comando de Missao: { "mission": "...", "namespace": "projeto_x" }
            if "mission" in message:
                mission = message.get("mission")
                namespace = message.get("namespace", "global")
                if not isinstance(mission, str) or not mission.strip() or len(mission) > 20_000:
                    await websocket.send_json({"type": "error", "data": {"message": "Missão vazia ou acima do limite de 20.000 caracteres."}})
                    continue
                if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", namespace):
                    await websocket.send_json({"type": "error", "data": {"message": "Namespace inválido."}})
                    continue
                
                # Cancela missao anterior se houver
                if current_mission_task and not current_mission_task.done():
                    current_mission_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await current_mission_task
                    logger.info("🛑 Missao anterior abortada.")

                logger.info(f"🎯 Nova Missao [{namespace}]: {mission}")
                
                # Dispara o Orquestrador Industrial
                current_mission_task = asyncio.create_task(
                    orchestrator.run_complex_mission(
                        mission=mission, 
                        namespace=namespace,
                        callback=stream_event
                    )
                )
                current_mission_task.add_done_callback(_report_task_failure)
            
    except WebSocketDisconnect:
        logger.info("🔌 WebSocket Agent desconectado")
    except Exception as e:
        logger.error(f"❌ Falha no WebSocket do Agente: {e}")
    finally:
        if current_mission_task and not current_mission_task.done():
            current_mission_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await current_mission_task
