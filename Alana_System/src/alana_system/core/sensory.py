import logging
import asyncio
from collections import deque, defaultdict
from typing import Optional, Dict, Any, Set
from datetime import datetime
import time
from alana_system.utils.background_tasks import task_manager

logger = logging.getLogger("alana.core.sensory")

class SensoryManager:
    """
    Gerenciador de Percepção Presente (Nível JARVIS).
    Mantém um buffer circular do que o sistema está vendo e ouvindo, 
    permitindo proatividade e contexto sensorial.
    """
    def __init__(self, buffer_size: int = 5):
        self.buffer_size = buffer_size
        self.vision_buffer = defaultdict(lambda: deque(maxlen=self.buffer_size))
        self.voice_buffer = defaultdict(lambda: deque(maxlen=self.buffer_size))
        self.active_streams: Dict[Any, str] = {} # websocket -> namespace
        self.last_alert_time: Dict[str, float] = defaultdict(float)
        self.cooldown_seconds = 15.0

    def update_vision(self, description: str, image_bytes: bytes, metadata: Optional[Dict[str, Any]] = None):
        """Adiciona percepcao, armazena bytes para validacao e verifica antecipacao."""
        metadata = metadata or {}
        namespace = metadata.get("namespace", metadata.get("location", "global"))
        self.vision_buffer[namespace].append({
            "content": description,
            "raw_bytes": image_bytes, # Guardamos os bytes para validacao posterior
            "meta": metadata,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"👁️ Buffer: {description[:50]}...")
        
        # Dispara verificacao de antecipacao em background
        task_manager.run_task(self.check_for_anticipation, namespace=namespace, name=f"anticipation_check_{namespace}")

    def add_voice_event(self, text: str, device_id: str, namespace: str = "global"):
        """Adiciona um evento de voz ao buffer sensorial."""
        self.voice_buffer[namespace].append({
            "content": text,
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"🎙️ Voice Buffer: {text[:50]}...")

    async def check_for_anticipation(self, namespace: str = "global"):
        """
        Analisa se o usuario esta focado em algo e precisa de ajuda proativa.
        Logica Industrial: Persistencia de foco em entidades tecnicas.
        """
        vision_buffer = self.vision_buffer[namespace]
        if len(vision_buffer) < 3:
            return

        # Pega as ultimas descricoes
        lasts = [f["content"].lower() for f in list(vision_buffer)[-3:]]
        
        # Keywords tecnicas expandidas (P4 Auditoria)
        tech_keywords = {"inversor", "painel", "circuito", "motor", "placa", "sensor", "arduino", "esp32", "servidor", "ponte", "transistor", "capacitor"}
        
        # Verifica se todos os ultimos 3 frames contem algum termo tecnico
        is_focused = all(any(kw in desc for kw in tech_keywords) for desc in lasts)
        
        if is_focused:
            current_time = time.time()
            if current_time - self.last_alert_time[namespace] > self.cooldown_seconds:
                logger.info("🎯 Foco tecnico persistente detectado.")
                await self.broadcast_alert("Percebi seu foco neste componente. Deseja uma análise técnica profunda ou busca de esquemáticos?", namespace)
                self.last_alert_time[namespace] = current_time
            else:
                logger.debug("🎯 Foco detectado, mas em cooldown para evitar spam.")

    def get_last_vision(self, namespace: str = "global") -> Optional[Dict[str, Any]]:
        """Recupera a última percepção visual para contexto (ex: 'O que é isso?')."""
        buffer = self.vision_buffer[namespace]
        return buffer[-1] if buffer else None

    def register_stream(self, websocket, namespace: str = "global"):
        """Registra um novo dispositivo (wearable) para receber alertas proativos."""
        self.active_streams[websocket] = namespace
        logger.info(f"📡 Dispositivo sensorial conectado. Total: {len(self.active_streams)}")

    def unregister_stream(self, websocket):
        """Remove um dispositivo desconectado."""
        self.active_streams.pop(websocket, None)
        logger.info(f"📡 Dispositivo sensorial desconectado. Total: {len(self.active_streams)}")

    async def broadcast_alert(self, message: str, namespace: str = "global"):
        """
        Envia uma mensagem imediata (voz/alerta) para todos os wearables conectados.
        Este é o núcleo da proatividade (JARVIS mode).
        """
        targets = [ws for ws, stream_namespace in self.active_streams.items() if stream_namespace == namespace]
        if not targets:
            logger.warning(f"📢 Alerta proativo gerado, mas nenhum dispositivo conectado: {message}")
            return
        
        logger.info(f"📢 Enviando Alerta Proativo: {message}")
        
        payload = {
            "type": "PROACTIVE_ALERT",
            "content": message,
            "priority": "high"
        }
        
        # Envio simultâneo para todos os dispositivos
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.error(f"❌ Falha ao enviar alerta para dispositivo: {e}")
                self.unregister_stream(ws)
