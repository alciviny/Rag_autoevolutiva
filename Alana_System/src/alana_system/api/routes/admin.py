import os
import logging
import re
from fastapi import APIRouter, Depends, Request, Query
from alana_system.core.config import LOG_FILE
from alana_system.api.dependencies import get_llm_engine, get_vector_store, get_graph_store
from alana_system.inference.llm_engine import LLMEngine

logger = logging.getLogger("alana.api.admin")
router = APIRouter(tags=["Admin"])

@router.get("/health")
async def health_check(
    llm: LLMEngine = Depends(get_llm_engine),
    vector_store = Depends(get_vector_store),
    graph_store = Depends(get_graph_store)
):
    """Verifica a saude dos componentes vitais."""
    return {
        "status": "online",
        "llm": "ok" if llm else "fail",
        "vector_store": "ok" if vector_store else "fail",
        "graph_store": "ok" if graph_store else "fail",
        "model": llm.model if llm else "N/A"
    }

@router.get("/status")
async def system_status(vector_store=Depends(get_vector_store)):
    """Retorna telemetria de hardware e banco de dados."""
    import torch
    gpu = torch.cuda.is_available()
    return {
        "device": "cuda" if gpu else "cpu",
        "gpu_name": torch.cuda.get_device_name(0) if gpu else "N/A",
        "vram_total": f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB" if gpu else "N/A",
        "vectors_count": vector_store.count() if vector_store else 0
    }

@router.get("/logs")
async def get_logs(lines: int = Query(100, ge=10, le=500)):
    """Retorna as ultimas linhas do log do sistema."""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                content = f.readlines()
                return {"logs": "".join(content[-lines:])}
        return {"logs": "Arquivo de log nao encontrado."}
    except Exception as e:
        return {"logs": f"Erro ao ler logs: {e}"}

@router.get("/graph/data")
async def get_graph_data(
    namespace: str = Query("global"),
    limit: int = Query(500, le=2000),
    version: int = Query(1),
    file: str = Query(None),
    graph_store=Depends(get_graph_store)
):
    """
    Retorna os dados do grafo formatados para visualizacao (Vis.js/D3).
    Otimizado para carregar tipos e relacoes em lote com filtro de namespace.
    """
    try:
        # Busca as relacoes filtradas por namespace, versao e documento (se fornecido)
        relations = graph_store.query_subgraph_by_namespace(namespace, limit=limit, version=version, file=file)
        
        nodes = []
        edges = []
        seen_nodes = {} # node_id -> type
        
        # Cores industriais por tipo
        color_map = {
            "Conceito": "#3b82f6", "Tecnologia": "#10b981", "Sistema": "#f59e0b",
            "Pessoa": "#8b5cf6", "Local": "#ef4444", "Evento": "#ec4899", "Ferramenta": "#6366f1"
        }

        for rel in relations:
            subj, obj, r_type = rel["subject"], rel["object"], rel["relation"]
            
            # Adiciona nos e suas propriedades
            for node_name in [subj, obj]:
                if node_name not in seen_nodes:
                    # Otimizacao: o query_subgraph_by_namespace agora ja traz o tipo se possivel
                    # Se nao trouxer, usamos default
                    e_type = rel.get(f"{'s' if node_name==subj else 'o'}_type", "Conceito")
                    e_desc = rel.get(f"{'s' if node_name==subj else 'o'}_desc", "")
                    
                    nodes.append({
                        "id": node_name,
                        "label": node_name,
                        "title": f"Tipo: {e_type}\nDescrição: {e_desc}" if e_desc else f"Tipo: {e_type}",
                        "color": color_map.get(e_type, "#94a3b8"),
                        "font": {"color": "#ffffff"}
                    })
                    seen_nodes[node_name] = e_type
            
            # Adiciona conexao
            edges.append({
                "from": subj, "to": obj, "label": r_type,
                "arrows": "to", "color": {"color": "rgba(255, 255, 255, 0.3)"},
                "font": {"size": 10, "color": "#94a3b8"}
            })
            
        return {"nodes": nodes, "edges": edges, "namespace": namespace}
    except Exception as e:
        logger.error(f"Erro ao exportar grafo: {e}")
        return {"nodes": [], "edges": []}

from alana_system.api.dependencies import get_llm_engine, get_vector_store, get_graph_store, get_experience_store

@router.get("/experiences")
async def get_experiences(
    namespace: str = Query("global"),
    limit: int = Query(20),
    experience_store = Depends(get_experience_store)
):
    """Retorna o historico de missoes e aprendizados (Timeline)."""
    try:
        # Busca todas as experiencias do namespace (usando busca vazia para listar recentes)
        experiences = experience_store._keyword_search("", namespace, limit)
        return {"experiences": experiences, "namespace": namespace}
    except Exception as e:
        logger.error(f"Erro ao buscar experiencias: {e}")
        return {"experiences": []}

@router.get("/spatial/data")
async def get_spatial_data(
    namespace: str = Query("global"),
    graph_store = Depends(get_graph_store)
):
    """Retorna entidades que possuem localizacao conhecida para o Mapeador Espacial."""
    try:
        # Query direta no SQLite via GraphStore
        with graph_store._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, type, last_location, last_seen FROM entities WHERE namespace = ? AND last_location != 'unknown'",
                (namespace,)
            )
            entities = [dict(row) for row in cursor.fetchall()]
            return {"entities": entities, "namespace": namespace}
    except Exception as e:
        logger.error(f"Erro ao buscar dados espaciais: {e}")
        return {"entities": []}

@router.get("/graph/hubs")
async def get_graph_hubs(
    namespace: str = Query("global"),
    limit: int = Query(10),
    graph_store=Depends(get_graph_store)
):
    """Retorna os principais Hubs (entidades mais conectadas) para visualizacao dinamica."""
    try:
        hubs = graph_store.top_hubs(limit=limit, namespace=namespace)
        return {"hubs": hubs, "namespace": namespace}
    except Exception as e:
        logger.error(f"Erro ao buscar hubs: {e}")
        return {"hubs": []}

@router.get("/graph/files")
async def get_graph_files(
    namespace: str = Query("global"),
    graph_store=Depends(get_graph_store)
):
    """Retorna a lista de documentos (source_doc) que possuem entidades no grafo."""
    try:
        with graph_store._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source_doc FROM relations WHERE namespace = ? AND source_doc IS NOT NULL", (namespace,))
            files = [row["source_doc"] for row in cursor.fetchall()]
            return {"files": files}
    except Exception as e:
        logger.error(f"Erro ao buscar arquivos do grafo: {e}")
        return {"files": []}
