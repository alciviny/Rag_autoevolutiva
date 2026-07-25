import logging
import json
import asyncio
from typing import Optional, Dict, Any
from fastapi import APIRouter, File, UploadFile, HTTPException, Request, Form, WebSocket, WebSocketDisconnect

from alana_system.iot.vision import VisionProcessor
from alana_system.iot.voice import VoiceProcessor
from alana_system.iot.hal import hal
from alana_system.inference.llm_engine import LLMEngine
from alana_system.utils.background_tasks import task_manager

logger = logging.getLogger("alana.iot.router")
iot_router = APIRouter(prefix="/iot", tags=["IoT Gateway"])

# Instancia leve para visao (usa API externa)
vision_processor = VisionProcessor()

@iot_router.post("/vision")
async def process_vision(
    request: Request,
    image: UploadFile = File(...),
    namespace: str = Form("global"),
    device_id: str = Form("default_device"),
    prompt: Optional[str] = Form("Descreva detalhadamente o que você vê nesta imagem.")
):
    """Analisa imagem enviada pelo dispositivo (ex: Oculos)."""
    # Registrar Heartbeat
    hal.register_heartbeat(device_id, "camera")
    
    try:
        contents = await image.read()
        logger.info(f"📸 [Vision] Analisando imagem no namespace '{namespace}'")
        
        description = await vision_processor.analyze_image(contents, prompt=prompt)
        
        # Alimenta o Buffer de Percepcao (JARVIS Mode)
        request.app.state.sensory_manager.update_vision(description, image_bytes=contents, metadata={"location": namespace, "device_id": device_id})
        
        # 4. Auto-Indexacao Espacial (Background Task)
        # Extrai entidades do que foi visto e mapeia para a localizacao (namespace)
        async def auto_index_vision(desc, ns):
            q_engine = request.app.state.query_engine
            graph_data = await q_engine.entity_extractor.extract_graph(f"Visão detectada em {ns}: {desc}")
            if graph_data.entities:
                q_engine.graph_store.add_knowledge(
                    graph_data, 
                    source_doc="vision_sensor", 
                    page_number=0, 
                    namespace=ns,
                    metadata={"location": ns}
                )
                # Dispara a curiosidade autonoma para as entidades novas/desconhecidas
                discovery = request.app.state.discovery_manager
                await discovery.evaluate_discovery(graph_data.entities, namespace=ns)
        
        task_manager.run_task(
            auto_index_vision, 
            description, 
            namespace, 
            name=f"vision_indexing_{namespace}", 
            namespace=namespace
        )
        
        return {
            "status": "success",
            "namespace": namespace,
            "description": description
        }
    except Exception as e:
        logger.error(f"Erro em /vision: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@iot_router.websocket("/stream")
async def iot_stream_endpoint(websocket: WebSocket):
    """Canal bi-direcional para proatividade (Alertas da Alana)."""
    sensory = websocket.app.state.sensory_manager
    await websocket.accept()
    sensory.register_stream(websocket)
    try:
        while True:
            # Mantém a conexão viva e recebe heartbeats se necessário
            data = await websocket.receive_text()
            logger.debug(f"📡 Heartbeat IoT: {data}")
    except WebSocketDisconnect:
        sensory.unregister_stream(websocket)
    except Exception as e:
        logger.error(f"Erro no stream IoT: {e}")
        sensory.unregister_stream(websocket)

@iot_router.get("/health")
async def get_hardware_health():
    """Retorna o estado de todos os dispositivos IoT registrados."""
    return {"devices": hal.get_device_status()}

@iot_router.post("/voice")
async def process_voice(
    request: Request, 
    audio: UploadFile = File(...),
    namespace: str = Form("global"),
    device_id: str = Form("default_device")
):
    """
    Interface sensorial inteligente. Transcreve voz e decide a acao usando IA.
    """
    # Registrar Heartbeat
    hal.register_heartbeat(device_id, "wearable_audio")
    
    try:
        contents = await audio.read()
        logger.info(f"🎤 [Voice] Audio recebido ({len(contents)} bytes) no namespace '{namespace}'")
        
        # 1. Transcricao Assincrona
        shared_transcriber = request.app.state.shared_transcriber
        voice_proc = VoiceProcessor(transcriber=shared_transcriber)
        
        ext = f".{audio.filename.split('.')[-1]}" if "." in audio.filename else ".wav"
        transcription = await voice_proc.transcribe_audio(contents, file_extension=ext)
        
        if not transcription:
            return {"status": "success", "message": "Silencio detectado."}

        logger.info(f"🗣️ Transcrito: '{transcription}'")
        
        # Adicionar o resultado ao sensor manager
        request.app.state.sensory_manager.add_voice_event(transcription, device_id)
        
        # 1. Processamento de Intencao (Arquitetura Centralizada)
        intent_res = await request.app.state.intent_manager.process_intent(transcription, namespace)
        
        if intent_res and intent_res.get("intent") != "NONE":
            return {
                "status": "success",
                "transcription": transcription,
                "intent": intent_res.get("intent"),
                "answer": intent_res.get("answer"),
                "source": intent_res.get("source", "intent_manager"),
                "namespace": namespace
            }

        # 2. Fluxo Conversacional (Fallback para conversa casual)
        llm = request.app.state.llm_engine
        answer = await llm.generate_answer(
            messages=[
                {"role": "system", "content": "Voce e a Alana, uma assistente de engenharia brilhante. Responda de forma concisa e util."},
                {"role": "user", "content": transcription}
            ]
        )

        return {
            "status": "success",
            "transcription": transcription,
            "intent": "CONVERSATION",
            "answer": answer,
            "source": "llm_chat",
            "namespace": namespace
        }

    except Exception as e:
        logger.error(f"Erro em /voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))

