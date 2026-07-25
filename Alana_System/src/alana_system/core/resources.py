import asyncio
import logging

logger = logging.getLogger("alana.core.resources")

class ResourceGatekeeper:
    """
    Gerencia o acesso ao hardware (GPU) para evitar sobrecarga.
    Implementa um semaforo global para inferencia.
    
    Abordagem profissional: Singleton Pattern.
    """
    _instance = None
    _semaphore = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ResourceGatekeeper, cls).__new__(cls)
            # Limitamos a 1 inferencia pesada por vez para estabilidade em GPUs de consumidor
            # Se voce tiver multiplas GPUs, este valor pode ser aumentado.
            cls._semaphore = asyncio.Semaphore(2)
            logger.info("🛡️ ResourceGatekeeper Inicializado | Semaforo de GPU: 2 slots")
        return cls._instance

    def get_semaphore(self):
        return self._semaphore

# Instancia singleton para uso em todo o sistema
gatekeeper = ResourceGatekeeper()
