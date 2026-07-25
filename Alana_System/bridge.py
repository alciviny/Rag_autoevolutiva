import os
import sys
import logging
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 1. Configuração de Infraestrutura Básica
os.makedirs("data/artifacts", exist_ok=True)
os.makedirs("data/sandbox", exist_ok=True)
os.makedirs("data/uploads", exist_ok=True)

# 2. Configuração de Path (Garante que o pacote 'alana_system' seja encontrado)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from alana_system.core.config import setup_logging, APP_TITLE, APP_VERSION, APP_DESCRIPTION
logger = setup_logging()

# 3. Ciclo de Vida e Motores (Lifespan Pattern)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerenciamento Industrial do Ciclo de Vida da Alana via Container Factory.
    """
    logger.info("🧠 Inicializando ecossistema industrial da Alana...")
    
    from alana_system.core.factory import container
    container.initialize_all()

    # Injeta os motores no state do FastAPI para compatibilidade com as rotas existentes
    for name, engine in container.engines.items():
        setattr(app.state, name, engine)
    
    # Intent Manager (especial case needs app.state or container)
    app.state.intent_manager = container.intent_manager

    # Como o LLMEngine agora eh um Router hibrido, acessamos o default_model
    default_model = getattr(app.state.llm_engine, "default_model", "Router-Híbrido")
    logger.info(f"🚀 Alana Bridge Online | Engine: {default_model}")
    
    # Tarefa de Limpeza Periódica de Tasks (Background)
    from alana_system.utils.background_tasks import task_manager
    async def periodic_task_cleanup():
        while True:
            await asyncio.sleep(3600) # 1 hora
            task_manager.cleanup_old_tasks()
            
    cleanup_task = asyncio.create_task(periodic_task_cleanup())
    
    yield
    
    cleanup_task.cancel()
    logger.info("🛑 Encerrando Alana Bridge. Limpando recursos...")

# 4. Inicialização do App FastAPI
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan
)

# 5. Middlewares
@app.middleware("http")
async def add_trace_id_middleware(request, call_next):
    from alana_system.utils.logging_context import set_trace_id
    trace_id = set_trace_id()
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# Habilita CORS com segurança industrial
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6. Inclusão de Rotas (Sistemas Modulares)
from alana_system.api.routes import admin, chat, ingestion, agent, system
from alana_system.iot.router import iot_router

app.include_router(admin.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(ingestion.router, prefix="/api")
app.include_router(agent.router) # O Agent usa websockets nativamente
app.include_router(iot_router, prefix="/api")
app.include_router(system.router, prefix="/api")

# 7. Ciclo de Vida e Arquivos Estáticos
# Servir arquivos de saída e frontend compilado (Vite dist)
app.mount("/data/artifacts", StaticFiles(directory="data/artifacts"), name="artifacts")
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    logger.info("📡 Servidor Alana iniciando na porta 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
