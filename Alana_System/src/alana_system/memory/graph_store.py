import sqlite3
import logging
import re
import uuid
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from alana_system.preprocessing.entity_extractor import KnowledgeGraphSchema

logger = logging.getLogger("alana.memory.graph")

class GraphStore:
    """
    Motor de Armazenamento em Grafo (SQLite).
    Gerencia entidades, relacoes, aliases e jobs de ingestao com foco em integridade industrial.
    """
    def __init__(self, db_path: str = "data/memory/alana_graph.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        """Cria uma conexao robusta com timeout e modo de seguranca para Windows/Docker."""
        import time
        for attempt in range(5):
            try:
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.row_factory = sqlite3.Row
                # Configuracoes industriais para alta concorrencia
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA cache_size=-64000;") # 64MB cache
                conn.execute("PRAGMA temp_store=MEMORY;")
                conn.execute("PRAGMA busy_timeout=30000;") # 30s
                return conn
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if ("disk i/o error" in msg or "database is locked" in msg) and attempt < 4:
                    logger.warning(f"⚠️ SQLite ocupado/erro I/O (Tentativa {attempt+1}/5). Re-tentando...")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise

    def _init_db(self) -> None:
        """Inicializa o esquema do banco de dados industrial."""
        with self._connect() as conn:
            cursor = conn.cursor()
            # Tabela de Entidades
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    namespace TEXT DEFAULT 'global',
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_location TEXT DEFAULT 'unknown',
                    UNIQUE(name, namespace)
                )
            """)
            
            # Migracao Industrial: Garante que todas as colunas existam
            cursor.execute("PRAGMA table_info(entities)")
            columns = [row[1] for row in cursor.fetchall()]
            
            missing_cols = []
            if "namespace" not in columns:
                cursor.execute("ALTER TABLE entities ADD COLUMN namespace TEXT DEFAULT 'global'")
                missing_cols.append("namespace")
            if "description" not in columns:
                cursor.execute("ALTER TABLE entities ADD COLUMN description TEXT")
                missing_cols.append("description")
            if "last_seen" not in columns:
                cursor.execute("ALTER TABLE entities ADD COLUMN last_seen TIMESTAMP")
                missing_cols.append("last_seen")
            if "last_location" not in columns:
                cursor.execute("ALTER TABLE entities ADD COLUMN last_location TEXT DEFAULT 'unknown'")
                missing_cols.append("last_location")
            
            if missing_cols:
                logger.info(f"🔧 Migração entities concluída: Adicionadas colunas {missing_cols}")
                conn.commit()
            # Tabela de Relacoes (Core do Grafo)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    object TEXT NOT NULL,
                    source_doc TEXT,
                    page_number INTEGER,
                    namespace TEXT DEFAULT 'global',
                    version INTEGER DEFAULT 1,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(subject, relation, object, source_doc, namespace, version)
                )
            """)
            
            # Auto-Migracao Industrial: Garante consistencia do esquema
            cursor.execute("PRAGMA table_info(relations)")
            rel_cols = [row[1] for row in cursor.fetchall()]
            if "version" not in rel_cols:
                logger.info("🔧 Migrando banco de dados: Adicionando coluna 'version' em relations...")
                cursor.execute("ALTER TABLE relations ADD COLUMN version INTEGER DEFAULT 1")
                conn.commit()
            # Tabela de Sinônimos/Aliases
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    alias TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    FOREIGN KEY(canonical_name) REFERENCES entities(name)
                )
            """)
            # Tabela de Controle de Ingestao (Checkpoints)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_hash TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    total_batches INTEGER DEFAULT 0,
                    completed_batches INTEGER DEFAULT 0,
                    error_message TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(file_hash, namespace)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_batches (
                    file_hash TEXT,
                    namespace TEXT,
                    batch_number INTEGER,
                    PRIMARY KEY(file_hash, namespace, batch_number)
                )
            """)
            
            # Removido: Tabela entity_embeddings agora foi descontinuada em favor do Qdrant (VectorStore).
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_namespace ON relations(namespace)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object)")
            
            # Tabela de Telemetria (Series Temporais do Lab)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_name TEXT NOT NULL,
                    value REAL,
                    unit TEXT,
                    raw_reading TEXT,
                    namespace TEXT DEFAULT 'global',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_entity ON telemetry(entity_name)")

            # Tabela de Sessões de Workflow (Resiliência Industrial - P3 Auditoria)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflow_sessions (
                    namespace TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    current_step_index INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_telemetry_reading(self, entity_name: str, value: Optional[float], unit: str, raw_reading: str, namespace: str = "global"):
        """Registra uma leitura tecnica capturada via Visao."""
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO telemetry (entity_name, value, unit, raw_reading, namespace)
                    VALUES (?, ?, ?, ?, ?)
                """, (entity_name, value, unit, raw_reading, namespace))
                conn.commit()
                logger.info(f"📊 Telemetria registrada: {entity_name} = {value} {unit}")
        except Exception as e:
            logger.error(f"Erro ao salvar telemetria: {e}")

    def get_entity(self, name: str, namespace: str = "global") -> Optional[Dict]:
        """Recupera metadados de uma entidade de forma segura (Abstracao de Infra - P2 Auditoria)."""
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM entities WHERE name = ? AND namespace = ?", 
                    (name, namespace)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Erro ao buscar entidade {name}: {e}")
            return None

    def normalize_name(self, name: str) -> str:
        """Normalizacao focada em precisao tecnica."""
        name = name.strip()
        if not name: return ""
        if len(name) <= 3:
            # Preserva original para siglas (ex: GPU, VCC) ou limpa se for comum
            return name.strip() if not name.isupper() else name.upper()
        words = name.split()
        if not words: return ""
        
        normalized_words = [words[0].capitalize()]
        connectives = {"de", "da", "do", "em", "com", "para", "e", "o", "a"}
        for word in words[1:]:
            lower_w = word.lower()
            if lower_w in connectives: normalized_words.append(lower_w)
            elif word.isupper() or any(c.isdigit() for c in word): normalized_words.append(word)
            else: normalized_words.append(word.capitalize())
        return " ".join(normalized_words)

    @lru_cache(maxsize=1024)
    def _resolve_canonical_name_cached(self, name: str) -> str:
        """Versao com cache para evitar IO excessivo em loop (Ponto 4 Auditoria)."""
        normalized = self.normalize_name(name)
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT canonical_name FROM entity_aliases WHERE alias = ?", (normalized,))
                row = cursor.fetchone()
                if row: return row["canonical_name"]
                cursor.execute("SELECT name FROM entities WHERE name = ?", (normalized,))
                row = cursor.fetchone()
                return row["name"] if row else normalized
        except Exception:
            return normalized

    def _resolve_canonical_name(self, cursor, name: str) -> str:
        """Resolve alias usando cursor existente (dentro de transacao)."""
        normalized = self.normalize_name(name)
        cursor.execute("SELECT canonical_name FROM entity_aliases WHERE alias = ?", (normalized,))
        row = cursor.fetchone()
        if row: return row["canonical_name"]
        cursor.execute("SELECT name FROM entities WHERE name = ?", (normalized,))
        row = cursor.fetchone()
        return row["name"] if row else normalized

    def add_knowledge(self, graph: KnowledgeGraphSchema, source_doc: str, page_number: int, namespace: str = "global", metadata: Dict = None) -> None:
        """Persiste um grafo completo extraído por IA com metadados espaciais."""
        if not graph: return
        metadata = metadata or {}
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                for entity in (graph.entities or []):
                    canonical = self._resolve_canonical_name(cursor, entity.name)
                    # Fusao Inteligente: Se ja existe, tenta mesclar metadados (Ponto Critico Auditoria)
                    cursor.execute("SELECT description, type FROM entities WHERE name = ? AND namespace = ?", (canonical, namespace))
                    existing = cursor.fetchone()
                    
                    if existing:
                        new_desc = entity.description if entity.description else ""
                        old_desc = existing["description"] if existing["description"] else ""
                        if new_desc and new_desc not in old_desc:
                            merged = f"{old_desc} | {new_desc}".strip(" | ")
                            cursor.execute("""
                                UPDATE entities SET description = ?, last_seen = CURRENT_TIMESTAMP, last_location = ? 
                                WHERE name = ? AND namespace = ?
                            """, (merged, metadata.get("location", "unknown"), canonical, namespace))
                        else:
                            cursor.execute("""
                                UPDATE entities SET last_seen = CURRENT_TIMESTAMP, last_location = ? 
                                WHERE name = ? AND namespace = ?
                            """, (metadata.get("location", "unknown"), canonical, namespace))
                    else:
                        cursor.execute("""
                            INSERT INTO entities (name, type, description, namespace, last_location) 
                            VALUES (?, ?, ?, ?, ?)
                        """, (canonical, entity.type, entity.description, namespace, metadata.get("location", "unknown")))
                
                for rel in (graph.relations or []):
                    subj = self._resolve_canonical_name(cursor, rel.subject)
                    obj = self._resolve_canonical_name(cursor, rel.object)
                    # Garante existencia com namespace
                    cursor.execute("INSERT OR IGNORE INTO entities (name, type, namespace) VALUES (?, ?, ?)", (subj, "Conceito", namespace))
                    cursor.execute("INSERT OR IGNORE INTO entities (name, type, namespace) VALUES (?, ?, ?)", (obj, "Conceito", namespace))
                    
                    cursor.execute("""
                        INSERT OR IGNORE INTO relations (subject, relation, object, source_doc, page_number, namespace, version)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (subj, rel.predicate, obj, source_doc, page_number, namespace, 1))
                conn.commit()
        except Exception as e:
            logger.error(f"Erro ao persistir conhecimento: {e}")

    def add_fact(self, subject: str, relation: str, object_name: str, source: str = "AGENT_DISCOVERY", namespace: str = "global") -> bool:
        """Adiciona um fato unico (Agent Discoveries)."""
        try:
            s_norm = self.normalize_name(subject)
            o_norm = self.normalize_name(object_name)
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO entities (name, type) VALUES (?, ?)", (s_norm, "Entity"))
                cursor.execute("INSERT OR IGNORE INTO entities (name, type) VALUES (?, ?)", (o_norm, "Entity"))
                cursor.execute("""
                    INSERT OR IGNORE INTO relations (subject, relation, object, source_doc, page_number, namespace)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (s_norm, relation.lower(), o_norm, source, 0, namespace))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erro ao adicionar fato: {e}")
            return False

    def query_subgraph(self, entity_names: List[str], limit: int = 50, namespace: str = "global") -> List[Dict]:
        """Consulta vizinhanca de 2-HOPS filtrada por namespace."""
        if not entity_names: return []
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                placeholders = ", ".join(["?"] * len(entity_names))
                query = f"""
                    SELECT DISTINCT subject, relation, object, source_doc, page_number
                    FROM relations WHERE (subject IN ({placeholders}) OR object IN ({placeholders})) AND namespace = ?
                    LIMIT ?
                """
                cursor.execute(query, (*entity_names, *entity_names, namespace, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    def query_subgraph_by_namespace(self, namespace: str, limit: int = 150, version: int = 1, file: str = None) -> List[Dict]:
        """Consulta relacoes e tipos em um unico JOIN (Otimizado para Dashboard) com suporte temporal."""
        query = """
            SELECT r.subject, r.relation, r.object, 
                   e1.type as s_type, e1.description as s_desc,
                   e2.type as o_type, e2.description as o_desc
            FROM relations r
            LEFT JOIN entities e1 ON r.subject = e1.name AND r.namespace = e1.namespace
            LEFT JOIN entities e2 ON r.object = e2.name AND r.namespace = e2.namespace
            WHERE r.namespace = ? AND r.version = ?
        """
        params = [namespace, version]
        if file:
            query += " AND r.source_doc = ?"
            params.append(file)
            
        query += " ORDER BY r.timestamp DESC LIMIT ?"
        params.append(limit)
        
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erro no export de subgrafo: {e}")
            return []

    def top_hubs(self, limit: int = 10, namespace: str = "global") -> List[Dict]:
        """Retorna as entidades mais conectadas do namespace."""
        query = """
            SELECT entity, COUNT(*) as total FROM (
                SELECT subject as entity FROM relations WHERE namespace = ?
                UNION ALL
                SELECT object as entity FROM relations WHERE namespace = ?
            ) GROUP BY entity ORDER BY total DESC LIMIT ?
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (namespace, namespace, limit))
            return [dict(row) for row in cursor.fetchall()]

    # --- Gestao de Jobs (Checkpoints) ---
    def register_ingestion_job(self, file_hash: str, filename: str, total_batches: int, namespace: str = "global"):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO ingestion_jobs (file_hash, filename, total_batches, namespace, status, completed_batches, updated_at)
                VALUES (?, ?, ?, ?, 'PENDING', 0, CURRENT_TIMESTAMP)
                ON CONFLICT(file_hash, namespace) DO UPDATE SET status = 'PENDING', updated_at = CURRENT_TIMESTAMP
            """, (file_hash, filename, total_batches, namespace))
            conn.commit()

    def mark_batch_complete(self, file_hash: str, namespace: str, batch_number: int):
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO processed_batches (file_hash, namespace, batch_number) VALUES (?, ?, ?)", (file_hash, namespace, batch_number))
            conn.execute("""
                UPDATE ingestion_jobs SET completed_batches = (SELECT COUNT(*) FROM processed_batches WHERE file_hash = ? AND namespace = ?),
                status = 'PROCESSING', updated_at = CURRENT_TIMESTAMP WHERE file_hash = ? AND namespace = ?
            """, (file_hash, namespace, file_hash, namespace))
            conn.commit()

    def get_processed_batches(self, file_hash: str, namespace: str) -> List[int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT batch_number FROM processed_batches WHERE file_hash = ? AND namespace = ?", (file_hash, namespace)).fetchall()
            return [row["batch_number"] for row in rows]

    def get_all_jobs(self) -> List[Dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM ingestion_jobs ORDER BY updated_at DESC").fetchall()]

    def update_job_status(self, file_hash: str, namespace: str, status: str, error_message: str = None) -> None:
        """Atualiza o status de um job de ingestão (PENDING, PROCESSING, COMPLETED, FAILED)."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE file_hash = ? AND namespace = ?
                """,
                (status, error_message, file_hash, namespace),
            )
            conn.commit()

    # (Os métodos save_entity_embedding e get_all_entity_embeddings foram descontinuados e migrados para o Qdrant)

    def add_alias(self, alias: str, canonical: str):
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO entity_aliases (alias, canonical_name) VALUES (?, ?)", (alias, canonical))
            conn.commit()

    def get_all_edges(self, namespace: str = "global", limit: Optional[int] = None) -> List[tuple]:
        """
        Retorna triplos filtrados por namespace (Ponto 1 Auditoria).
        Garante isolamento e evita carregamento total desnecessario.
        """
        try:
            with self._connect() as conn:
                query = "SELECT subject, relation, object FROM relations WHERE namespace = ?"
                params = [namespace]
                
                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                    
                rows = conn.execute(query, tuple(params)).fetchall()
                return [(r["subject"], r["relation"], r["object"]) for r in rows]
        except Exception as e:
            logger.error(f"Erro ao recuperar arestas do grafo: {e}")
            return []

    # --- Persistencia de Workflow (P3 Auditoria) ---
    def save_workflow_session(self, namespace: str, workflow_name: str, step_index: int):
        """Salva o progresso do guia tecnico no banco."""
        try:
            with self._connect() as conn:
                conn.execute("""
                    INSERT INTO workflow_sessions (namespace, workflow_name, current_step_index, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(namespace) DO UPDATE SET 
                        workflow_name = EXCLUDED.workflow_name,
                        current_step_index = EXCLUDED.current_step_index,
                        updated_at = CURRENT_TIMESTAMP
                """, (namespace, workflow_name, step_index))
                conn.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar sessao de workflow: {e}")

    def get_workflow_session(self, namespace: str) -> Optional[Dict]:
        """Recupera sessao ativa para o usuario/dispositivo."""
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM workflow_sessions WHERE namespace = ?", (namespace,)).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Erro ao recuperar sessao de workflow: {e}")
            return None

    def delete_workflow_session(self, namespace: str):
        """Remove sessao concluida ou abortada."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM workflow_sessions WHERE namespace = ?", (namespace,))
                conn.commit()
        except Exception as e:
            logger.error(f"Erro ao deletar sessao de workflow: {e}")

    def count_entities(self) -> int:
        """Retorna a quantidade total de entidades distintas registradas no banco."""
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM entities").fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Erro ao contar entidades: {e}")
            return 0

    def entity_degree(self, name: str) -> Dict[str, int]:
        """Retorna o grau de entrada (in) e saida (out) de uma entidade no grafo."""
        try:
            normalized = self.normalize_name(name)
            with self._connect() as conn:
                in_degree = conn.execute("SELECT COUNT(*) FROM relations WHERE object = ?", (normalized,)).fetchone()[0]
                out_degree = conn.execute("SELECT COUNT(*) FROM relations WHERE subject = ?", (normalized,)).fetchone()[0]
                return {"in": in_degree, "out": out_degree}
        except Exception as e:
            logger.error(f"Erro ao obter grau da entidade {name}: {e}")
            return {"in": 0, "out": 0}

    def infer_transitive_relations(self, max_hops: int = 3) -> int:
        """Infere relacoes transitivas e salva-as no banco."""
        try:
            with self._connect() as conn:
                # 1. Carrega todas as relacoes em memoria
                rows = conn.execute("SELECT subject, relation, object, namespace FROM relations").fetchall()
                if not rows:
                    return 0
                
                adj = {}
                for r in rows:
                    adj.setdefault(r["subject"], {}).setdefault(r["namespace"], []).append(r["object"])

                # 2. Computa caminhos transitivos de ate max_hops
                inferred_triples = []
                for start_node in adj:
                    for ns in adj[start_node]:
                        # BFS para achar todos os nos alcançaveis por caminhos de ate max_hops saltos
                        queue = [(start_node, 0)]
                        visited = {start_node}
                        while queue:
                            curr, depth = queue.pop(0)
                            if 1 < depth <= max_hops:
                                inferred_triples.append((start_node, "inferred_transitive", curr, ns))
                            if depth < max_hops:
                                for neighbor in adj.get(curr, {}).get(ns, []):
                                    if neighbor not in visited:
                                        visited.add(neighbor)
                                        queue.append((neighbor, depth + 1))
                
                # 3. Insere no banco as relacoes transitivas inferidas
                inferred_count = 0
                for subj, rel, obj, ns in inferred_triples:
                    # Nao reinsere se ja existir
                    existing = conn.execute(
                        "SELECT 1 FROM relations WHERE subject = ? AND relation = ? AND object = ? AND namespace = ?",
                        (subj, rel, obj, ns)
                    ).fetchone()
                    if not existing:
                        conn.execute("""
                            INSERT INTO relations (subject, relation, object, source_doc, page_number, namespace)
                            VALUES (?, ?, ?, 'INFERENCE_ENGINE', 0, ?)
                        """, (subj, rel, obj, ns))
                        inferred_count += 1
                conn.commit()
                return inferred_count
        except Exception as e:
            logger.error(f"Erro ao inferir relacoes transitivas: {e}")
            return 0

    def trending_entities(self, days: int = 7) -> List[Dict]:
        """Retorna as entidades vistas recentemente nos ultimos N dias ordenadas por frequencia."""
        try:
            from datetime import datetime, timedelta
            limit_date = (datetime.now() - timedelta(days=days)).isoformat()
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT name as entity, last_seen, last_location 
                    FROM entities 
                    ORDER BY last_seen DESC 
                    LIMIT 20
                """).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Erro ao obter entidades em tendencia: {e}")
            return []
