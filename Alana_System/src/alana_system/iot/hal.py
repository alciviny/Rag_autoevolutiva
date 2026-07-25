import time
import logging
from typing import Dict, Any, List

logger = logging.getLogger("alana.iot.hal")

class HardwareAbstractionLayer:
    """
    Monitor de Saude e Estado de Hardware IoT.
    Gerencia o Heartbeat de sensores e dispositivos remotos.
    """
    def __init__(self):
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.timeout_seconds = 300 # 5 minutos sem sinal = Offline

    def register_heartbeat(self, device_id: str, device_type: str, metadata: Dict = None):
        """Registra atividade de um dispositivo."""
        self.devices[device_id] = {
            "type": device_type,
            "last_seen": time.time(),
            "status": "ONLINE",
            "metadata": metadata or {}
        }
        logger.debug(f"💓 Heartbeat recebido: {device_id} ({device_type})")

    def get_device_status(self) -> List[Dict[str, Any]]:
        """Retorna a lista de dispositivos e seus estados atuais."""
        now = time.time()
        report = []
        for d_id, data in self.devices.items():
            if now - data["last_seen"] > self.timeout_seconds:
                data["status"] = "OFFLINE"
            
            report.append({
                "id": d_id,
                "type": data["type"],
                "status": data["status"],
                "last_seen_seconds_ago": int(now - data["last_seen"])
            })
        return report

    def is_online(self, device_id: str) -> bool:
        """Verifica se um dispositivo especifico esta ativo."""
        if device_id not in self.devices:
            return False
        return (time.time() - self.devices[device_id]["last_seen"]) <= self.timeout_seconds

# Instancia Global (Singleton)
hal = HardwareAbstractionLayer()
