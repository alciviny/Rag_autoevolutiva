"""
API Endpoints for Alana LLM System.

This module provides REST API endpoints for interacting with the Alana LLM system.
Includes ingestion, querying, and deep search functionalities.

Features:
- FastAPI-based endpoints.
- Dependency Injection via AlanaContainer.
- Multi-tenant namespace support.
- Async operations for scalability.
"""

import json
import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import asyncio

from ..ingestion.pdf_loader import PDFLoader
from ..core.factory import container

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Alana LLM API", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Inicializa todos os motores industriais através da Fábrica na inicialização da API."""
    logger.info("Iniciando Alana API...")
    container.initialize_all()

# Pydantic models for requests/responses
class QueryRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5
    namespace: str = "global"

class QueryResponse(BaseModel):
    answer: str
    sources: List[str]
    namespace: str

class DeepSearchRequest(BaseModel):
    query: str
    namespace: str = "global"

class DeepSearchResponse(BaseModel):
    report: str
    stored: bool

class IngestionResponse(BaseModel):
    message: str
    documents_processed: int

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "Alana LLM API is running"}

@app.post("/query", response_model=QueryResponse)
async def query_knowledge(request: QueryRequest):
    """
    Query the knowledge base.
    
    Performs True Semantic RAG: retrieves relevant context and generates answer.
    """
    try:
        query_engine = container.get("query_engine")
        if not query_engine:
            raise ValueError("QueryEngine não está inicializado.")
            
        answer = query_engine.answer_query(request.question)
        sources = ["graph_memory", "vector_memory"]
        logger.info(f"Query processed: {request.question} no namespace '{request.namespace}'")
        
        return QueryResponse(answer=answer, sources=sources, namespace=request.namespace)
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail="Query processing failed")

@app.post("/deep-search", response_model=DeepSearchResponse)
async def perform_deep_search(request: DeepSearchRequest, background_tasks: BackgroundTasks):
    """
    Perform deep web search, generate report, and store in graph.
    Runs asynchronously in background for long operations.
    """
    try:
        background_tasks.add_task(_run_deep_search, request.query, request.namespace)
        logger.info(f"Deep search initiated: {request.query} no namespace '{request.namespace}'")
        return {"message": "Deep search started. Check logs for completion."}
    except Exception as e:
        logger.error(f"Deep search failed: {e}")
        raise HTTPException(status_code=500, detail="Deep search failed")

async def _run_deep_search(query: str, namespace: str):
    """Background task for deep search."""
    try:
        deep_search_agent = container.get("deep_search_agent")
        result = await deep_search_agent.perform_deep_search(query)
        logger.info(f"Deep search completed: {query}, stored: {result.get('stored', False)}")
    except Exception as e:
        logger.error(f"Background deep search failed: {e}")

@app.post("/ingest-pdf", response_model=IngestionResponse)
async def ingest_pdf(file: UploadFile = File(...)):
    """
    Ingest a PDF file.
    Uploads and processes PDF, extracting and storing knowledge.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        
        loader = PDFLoader(raw_dir="/tmp")
        extracted = loader.discover_and_extract()
        
        processed = len(extracted)
        
        logger.info(f"PDF ingested: {file.filename}, documents: {processed}")
        return IngestionResponse(
            message="PDF ingested successfully",
            documents_processed=processed
        )
    except Exception as e:
        logger.error(f"PDF ingestion failed: {e}")
        raise HTTPException(status_code=500, detail="PDF ingestion failed")

# --- Agent WebSocket ---

@app.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    """
    WebSocket para comunicação em tempo real com a Alana Engenheira.
    Envia pensamentos, ações e resultados conforme acontecem.
    """
    await websocket.accept()
    
    # Adquire o Engenheiro oficial via DI Container (Garante acesso ao Cérebro e Grafo)
    orchestrator = container.get("orchestrator")
    if not orchestrator:
        await websocket.send_json({"type": "error", "data": {"message": "Orquestrador não inicializado na Factory."}})
        await websocket.close()
        return
        
    engine = orchestrator.engineer
    
    # Callback adaptado para o novo formato de eventos
    async def send_event(event_type: str, data: dict):
        try:
            await websocket.send_json({"type": event_type, "data": data})
        except Exception:
            pass # Socket fechado
            
    try:
        while True:
            # Espera o comando inicial ou novos comandos
            data = await websocket.receive_text()
            request = json.loads(data)
            mission = request.get("mission")
            namespace = request.get("namespace", "global")
            
            if mission:
                # O motor agora é invocado passando o callback diretamente
                await engine.run_mission(mission, namespace=namespace, event_callback=send_event)
            else:
                await websocket.send_json({"type": "error", "data": {"message": "Nenhuma missão fornecida."}})
                
    except WebSocketDisconnect:
        logger.info("Cliente desconectado do WebSocket da Alana.")
    except Exception as e:
        logger.error(f"Erro no WebSocket do Agente: {e}")
        try:
            await websocket.send_json({"type": "error", "data": {"message": str(e)}})
        except:
            pass

@app.get("/health")
async def health_check():
    """Detailed health check validating the DI Container."""
    llm = container.get("llm_engine")
    return {
        "status": "healthy" if llm else "degraded",
        "container": "initialized" if llm else "uninitialized"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)