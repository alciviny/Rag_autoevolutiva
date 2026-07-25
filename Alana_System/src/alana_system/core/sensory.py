import logging
import asyncio
from collections import deque
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
        self.vision_buffer = deque(maxlen=buffer_size)
        self.voice_buffer = deque(maxlen=buffer_size)
        self.active_streams: Set[Any] = set() # Conexões WebSocket ativas (dispositivos)
        self.last_alert_time = 0.0
        self.cooldown_seconds = 15.0

    def update_vision(self, description: str, image_bytes: bytes, metadata: Optional[Dict[str, Any]] = None):
        """Adiciona percepcao, armazena bytes para validacao e verifica antecipacao."""
        self.vision_buffer.append({
            "content": description,
            "raw_bytes": image_bytes, # Guardamos os bytes para validacao posterior
            "meta": metadata or {},
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"👁️ Buffer: {description[:50]}...")
        
        # Dispara verificacao de antecipacao em background
        task_manager.run_task(self.check_for_anticipation, name="anticipation_check")

    def add_voice_event(self, text: str, device_id: str):
        """Adiciona um evento de voz ao buffer sensorial."""
        self.voice_buffer.append({
            "content": text,
            "device_id": device_id,
            "timestamp": datetime.now().isoformat()
        })
        logger.debug(f"🎙️ Voice Buffer: {text[:50]}...")

    async def check_for_anticipation(self):
        """
        Analisa se o usuario esta focado em algo e precisa de ajuda proativa.
        Logica Industrial: Persistencia de foco em entidades tecnicas.
        """
        if len(self.vision_buffer) < 3:
            return

        # Pega as ultimas descricoes
        lasts = [f["content"].lower() for f in list(self.vision_buffer)[-3:]]
        
        # Keywords tecnicas expandidas (P4 Auditoria)
        tech_keywords = {"inversor", "painel", "circuito", "motor", "placa", "sensor", "arduino", "esp32", "servidor", "ponte", "transistor", "capacitor"}
        
        # Verifica se todos os ultimos 3 frames contem algum termo tecnico
        is_focused = all(any(kw in desc for kw in tech_keywords) for desc in lasts)
        
        if is_focused:
            current_time = time.time()
            if current_time - self.last_alert_time > self.cooldown_seconds:
                logger.info("🎯 Foco tecnico persistente detectado.")
                await self.broadcast_alert("Percebi seu foco neste componente. Deseja uma análise técnica profunda ou busca de esquemáticos?")
                self.last_alert_time = current_time
            else:
                logger.debug("🎯 Foco detectado, mas em cooldown para evitar spam.")

    def get_last_vision(self) -> Optional[Dict[str, Any]]:
        """Recupera a última percepção visual para contexto (ex: 'O que é isso?')."""
        return self.vision_buffer[-1] if self.vision_buffer else None

    def register_stream(self, websocket):
        """Registra um novo dispositivo (wearable) para receber alertas proativos."""
        self.active_streams.add(websocket)
        logger.info(f"📡 Dispositivo sensorial conectado. Total: {len(self.active_streams)}")

    def unregister_stream(self, websocket):
        """Remove um dispositivo desconectado."""
        self.active_streams.discard(websocket)
        logger.info(f"📡 Dispositivo sensorial desconectado. Total: {len(self.active_streams)}")

    async def broadcast_alert(self, message: str):
        """
        Envia uma mensagem imediata (voz/alerta) para todos os wearables conectados.
        Este é o núcleo da proatividade (JARVIS mode).
        """
        if not self.active_streams:
            logger.warning(f"📢 Alerta proativo gerado, mas nenhum dispositivo conectado: {message}")
            return
        
        logger.info(f"📢 Enviando Alerta Proativo: {message}")
        
        payload = {
            "type": "PROACTIVE_ALERT",
            "content": message,
            "priority": "high"
        }
        
        # Envio simultâneo para todos os dispositivos
        for ws in list(self.active_streams):
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.error(f"❌ Falha ao enviar alerta para dispositivo: {e}")
                self.unregister_stream(ws)
