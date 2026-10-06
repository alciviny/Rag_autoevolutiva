import sqlite3
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..embeddings.embedder import EmbeddedChunk
import numpy as np
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger("alana.memory.experience")


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()

class ExperienceStore:
    """
    Memória Episódica (Experiências do Agente). 
    Agora com isolamento por Namespace e suporte industrial a checkpoints.
    """

    def __init__(self, 
                 db_path: str = "alana_memoria_local/experiences.db",
                 vector_store: Any = None,
                 embedder: Any = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_store = vector_store
        self.embedder = embedder
        self._init_db()

    def _connect(self):
        """Cria uma conexao robusta para a Memória Episódica."""
        import time
        for attempt in range(5):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0, factory=_ClosingConnection)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=30000;")
                return conn
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 4:
                    time.sleep(0.5)
                    continue
                raise

    def _init_db(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY,
                    mission_name TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    winning_strategy TEXT NOT NULL,
                    code_snippets TEXT,
                    related_entities TEXT,
                    outcome TEXT DEFAULT 'SUCCESS',
                    namespace TEXT DEFAULT 'global',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_experience(self, 
                        mission_name: str, 
                        description: str, 
                        strategy: str, 
                        code_snippets: List[str] = None,
                        entities: List[str] = None,
                        namespace: str = "global"):
        """
        Salva a lição no SQLite e indexa no Qdrant de forma compatível com a nova API.
        """
        exp_id = str(uuid.uuid4())
        
        try:
            # 1. Persistência no SQLite
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO experiences (id, mission_name, task_description, winning_strategy, code_snippets, related_entities, namespace)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    exp_id, mission_name, description, strategy, 
                    json.dumps(code_snippets or []), json.dumps(entities or []), namespace
                ))
                conn.commit()

            # 2. Indexação Vetorial (Qdrant)
            if self.vector_store and self.embedder:
                text_to_embed = f"MISSÃO: {mission_name}\nDESCRIÇÃO: {description}\nESTRATÉGIA: {strategy}"
                vector = self.embedder.embed_texts([text_to_embed])[0]
                
                # Criamos um EmbeddedChunk fake para satisfazer a API do VectorStore
                chunk = EmbeddedChunk(
                    chunk_id=exp_id,
                    page_number=0,
                    text=text_to_embed[:500], # Resumo para o payload
                    source_name=f"experience:{mission_name}",
                    embedding=vector,
                    record_type="experience",
                )
                
                self.vector_store.upsert_embeddings([chunk], namespace=namespace)
            
            logger.info(f"🧠 Memória Episódica [{namespace}]: '{mission_name}' imortalizada.")
        except Exception as e:
            logger.error(f"Falha ao imortalizar experiência: {e}")

    def recall_experiences(self, query: str, namespace: str = "global", limit: int = 2) -> List[Dict]:
        """
        Busca lições do passado usando busca vetorial filtrada por namespace.
        """
        if not self.vector_store or not self.embedder:
            logger.warning("Qdrant/Embedder ausentes. Usando busca básica.")
            return self._keyword_search(query, namespace, limit)

        try:
            # 1. Busca no Qdrant
            query_vector = self.embedder.embed_texts([query])[0]
            matches = self.vector_store.search(
                query_vector,
                top_k=limit,
                namespace=namespace,
                filters=Filter(must=[FieldCondition(key="record_type", match=MatchValue(value="experience"))]),
            )
            
            # IDs de experiências similares (no VectorStore o original_id guarda o exp_id)
            exp_ids = [m["chunk_id"] for m in matches if m["chunk_id"]]
            
            if not exp_ids:
                return self._keyword_search(query, namespace, limit)

            # 2. Recupera detalhes do SQLite
            with self._connect() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(exp_ids))
                cursor.execute(f"SELECT * FROM experiences WHERE id IN ({placeholders}) AND namespace = ?", (*exp_ids, namespace))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro no Recall Semântico: {e}")
            return []

    def _keyword_search(self, query: str, namespace: str, limit: int) -> List[Dict]:
        """Busca flexível por palavras-chave com filtro de namespace."""
        if not query: return []
            
        words = [f"%{w.strip()}%" for w in query.split() if len(w) > 3]
        if not words: words = [f"%{query}%"]

        with self._connect() as conn:
            cursor = conn.cursor()
            
            clauses = " OR ".join(["task_description LIKE ?" for _ in words])
            cursor.execute(f"SELECT * FROM experiences WHERE ({clauses}) AND namespace = ? ORDER BY timestamp DESC LIMIT ?", (*words, namespace, limit))
            return [dict(row) for row in cursor.fetchall()]

    def list_recent(self, namespace: str = "global", limit: int = 20) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM experiences WHERE namespace = ? ORDER BY timestamp DESC LIMIT ?",
                (namespace, max(1, min(limit, 100))),
            ).fetchall()
            return [dict(row) for row in rows]
