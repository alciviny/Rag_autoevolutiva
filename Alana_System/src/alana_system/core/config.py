import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from pathlib import Path

# Carrega variáveis de ambiente
load_dotenv()

# Configurações de Caminhos
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = BASE_DIR / "alana.log"

# Configuração de Logging Centralizada
def setup_logging():
    from alana_system.utils.logging_context import TraceIDFilter
    
    # Mantém 5 backups de 10MB cada
    handler = RotatingFileHandler(
        LOG_FILE, 
        maxBytes=10*1024*1024, 
        backupCount=5, 
        encoding="utf-8"
    )
    
    logging.basicConfig(
        level=logging.INFO,
        force=True,
        handlers=[
            handler,
            logging.StreamHandler()
        ],
        format="%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s - %(message)s"
    )

    # Injeta o Trace ID em todos os registros
    for h in logging.root.handlers:
        h.addFilter(TraceIDFilter())

    # SILENCIAMENTO DE VERBOSIDADE (Auditoria de Elite)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)

    return logging.getLogger("AlanaSystem")

# Configurações do App
APP_TITLE = "Alana AI System"
APP_VERSION = "2.2.0"
APP_DESCRIPTION = "Sistema de Engenharia Autônoma e RAG Multimodal"

# Configurações de Modelos (Defaults)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "ollama/llama3.1")
VISION_MODEL_CLOUD = os.getenv("VISION_MODEL_CLOUD", "gemini/gemini-2.0-flash")
VISION_MODEL_LOCAL = os.getenv("VISION_MODEL_LOCAL", "ollama/moondream")
SOVEREIGN_MODE = os.getenv("SOVEREIGN_MODE", "true").lower() == "true" # Força uso local se true
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
EMBEDDER_DEVICE = os.getenv("EMBEDDER_DEVICE", "cpu")
