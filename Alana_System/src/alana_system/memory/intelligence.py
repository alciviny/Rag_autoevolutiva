import logging
from typing import List, Dict, Any, Optional
from .graph_store import GraphStore
from .vector_store import VectorStore
from ..inference.llm_engine import LLMEngine
from ..core.binary_bridge import BinaryBridge
from ..embeddings.embedder import TextEmbedder
import numpy as np

logger = logging.getLogger("alana.memory.intelligence")

class GraphIntelligence:
    """
    O 'Cérebro Analítico' da Alana agora focado em lógica, delegando IO para a BinaryBridge.
    """
    
    def __init__(self, graph_store: GraphStore, vector_store: VectorStore, llm_engine: LLMEngine, embedder: TextEmbedder, entity_vector_store: Optional[VectorStore] = None):
        self.graph_store = graph_store
        self.vector_store = vector_store
        self.llm_engine = llm_engine
        self.embedder = embedder
        self.bridge = BinaryBridge("graph_turbo.exe")
        
        # Qdrant VectorStore exclusivo para reconciliação de entidades
        # Dimensão obtida dinamicamente do modelo de embedding
        self.entity_vector_store = entity_vector_store or VectorStore(
            collection_name="alana_entities",
            vector_dim=self.embedder.model.get_sentence_embedding_dimension()
        )

    def get_neighborhood(self, entity_name: str, hops: int = 1, namespace: str = "global") -> str:
        """Explora a vizinhança usando o motor Turbo em Go filtrada por namespace."""
        normalized = self.graph_store.normalize_name(entity_name)
        
        # Proteção Industrial: Evita carregar grafos massivos em memória
        edges = self.graph_store.get_all_edges(namespace=namespace, limit=10000)
        if len(edges) >= 10000:
            logger.error(f"🚨 Grafo Crítico ({len(edges)} arestas). O carregamento em massa foi interrompido para evitar OOM.")
            return "Erro: Grafo grande demais para visualização em tempo real. Use queries específicas."
        
        try:
            neighbors = self.bridge.call({
                "edges": [{"from": e[0], "to": e[1], "type": e[2]} for e in edges],
                "source": normalized,
                "mode": "neighbors"
            })
            
            if not neighbors:
                return f"Entidade '{normalized}' sem conexoes conhecidas."

            res = [f"- {normalized} --> {n}" for n in neighbors]
            return f"--- VIZINHANCA TURBO DE '{normalized}' ---\n" + "\n".join(res[:30])
        except Exception as e:
            return f"Erro na exploracao do grafo: {e}"

    def find_path(self, source: str, target: str, namespace: str = "global") -> str:
        """Encontra o caminho mais curto entre dois conceitos no namespace."""
        edges = self.graph_store.get_all_edges(namespace=namespace)
        if len(edges) > 5000:
            logger.warning(f"🚨 Grafo muito grande ({len(edges)} arestas). Busca de caminho pode ser lenta.")
        try:
            path = self.bridge.call({
                "edges": [{"from": e[0], "to": e[1], "type": e[2]} for e in edges],
                "source": self.graph_store.normalize_name(source),
                "target": self.graph_store.normalize_name(target),
                "mode": "path"
            })
            
            if not path:
                return f"Nao ha conexao entre '{source}' e '{target}'."
            
            return f"CONEXAO DESCOBERTA: {' -> '.join(path)}"
        except Exception as e:
            return f"Erro ao buscar caminho: {e}"

    async def analyze_patterns(self, focus_entities: List[str] = None, namespace: str = "global") -> Dict[str, Any]:
        """
        Analisa o grafo em busca de padrões ocultos ou anomalias dentro de um namespace.
        """
        if not focus_entities:
            return {"insights": []}

        logger.info(f"Analisando padrões [{namespace}] para: {focus_entities}")

        facts = self.graph_store.query_subgraph(focus_entities, limit=20, namespace=namespace)

        if not facts:
            return {"insights": ["Nenhum padrão estrutural detectado para estas entidades."]}

        fact_str = "\n".join([f"{f['subject']} --[{f['relation']}]--> {f['object']}" for f in facts])

        system_prompt = (
            "Você é o Cérebro Analítico da Alana. Analise estes fatos e identifique 1 ou 2 padrões implícitos "
            "ou riscos técnicos que não estão óbvios. Seja extremamente conciso e técnico."
        )
        user_content = f"FATOS:\n{fact_str}\n\nINSIGHTS (em português, formato lista):"

        try:
            response = await self.llm_engine.generate_answer(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
            )
            insights = [line.strip("- ").strip() for line in response.split("\n") if line.strip()]
            return {"insights": insights[:3]}
        except Exception as e:
            logger.error(f"Erro na análise de padrões: {e}")
            return {"insights": ["Falha técnica ao processar padrões cognitivos."]}

    async def analyze_propagation(self, target_entity: str, hops: int = 3, namespace: str = "global") -> Dict[str, Any]:
        """
        Analisa o impacto de uma falha em 'target_entity' propagando-se pelo grafo
        em até 'hops' saltos (simulação de Teoria do Caos) no namespace.
        """
        normalized = self.graph_store.normalize_name(target_entity)
        edges = self.graph_store.get_all_edges(namespace=namespace)

        # BFS simples sobre as arestas em memória (sem depender do motor Go)
        adjacency: Dict[str, List[str]] = {}
        for subj, _rel, obj in edges:
            adjacency.setdefault(subj, []).append(obj)

        visited: set = set()
        frontier = {normalized}
        for _ in range(hops):
            next_frontier: set = set()
            for node in frontier:
                for neighbor in adjacency.get(node, []):
                    if neighbor not in visited:
                        next_frontier.add(neighbor)
            visited.update(frontier)
            frontier = next_frontier

        affected = list(visited - {normalized})

        if not affected:
            return {
                "start_node": normalized,
                "total_impact_count": 0,
                "risk_assessment": "Entidade isolada ou inexistente no grafo. Sem propagação detectada.",
            }

        affected_str = ", ".join(affected[:20])
        system_prompt = (
            "Você é um Engenheiro de Confiabilidade Sênior. "
            "Avalie o impacto de uma falha no componente indicado com base nas entidades afetadas. "
            "Seja direto e técnico. Responda em uma sentença por risco identificado."
        )
        user_content = (
            f"FALHA EM: {normalized}\n"
            f"ENTIDADES AFETADAS EM {hops} SALTOS: {affected_str}\n\n"
            "AVALIAÇÃO DE RISCO:"
        )

        try:
            risk = await self.llm_engine.generate_answer(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
            )
        except Exception as e:
            logger.error(f"Erro na avaliação de risco: {e}")
            risk = "Não foi possível gerar avaliação de risco automática."

        return {
            "start_node": normalized,
            "total_impact_count": len(affected),
            "risk_assessment": risk,
        }

    async def reconcile_entity(self, name: str, namespace: str = "global") -> str:
        """
        Reconciliador Semântico Industrial (Ponto 3 Auditoria).
        Usa busca vetorial O(1) no Qdrant para encontrar se 'name' já existe com outro termo,
        evitando gargalo O(N^2) que ocorria no SQLite iterando em Python.
        """
        normalized = self.graph_store.normalize_name(name)
        new_emb = self.embedder.embed_query(normalized)
        
        # Busca a entidade mais parecida semanticamente no Qdrant
        results = self.entity_vector_store.search(
            query_vector=new_emb,
            top_k=1,
            namespace=namespace
        )
        
        if results:
            best_match = results[0]
            # Threshold Industrial: 0.92 (ajustado para precisão técnica)
            if best_match["score"] > 0.92 and best_match.get("entity_name"):
                matched_name = best_match["entity_name"]
                if matched_name != normalized:
                    logger.info(f"🔗 Reconciliacao Semantica (Qdrant): '{normalized}' unificado a '{matched_name}' (Score: {best_match['score']:.4f})")
                    self.graph_store.add_alias(normalized, matched_name)
                return matched_name
                
        # Novo conceito único: Salva no VectorStore (Qdrant)
        self.entity_vector_store.upsert_entities(
            entities=[{"name": normalized, "embedding": new_emb.tolist()}],
            namespace=namespace
        )
        return normalized

    async def get_seed_entities(self, query: str, top_k: int = 5, namespace: str = "global") -> List[str]:
        """
        True Semantic Graph Entrypoint.
        Busca os nós mais relevantes matematicamente para iniciar a navegação no Grafo.
        Desacopla a busca de regras gramaticais e ferramentas lentas (spaCy).
        """
        query_emb = self.embedder.embed_query(query)
        results = self.entity_vector_store.search(
            query_vector=query_emb,
            top_k=top_k,
            namespace=namespace,
            # Threshold generoso para capturar entidades relacionadas à pergunta
            score_threshold=0.55 
        )
        
        seeds = [res["entity_name"] for res in results if res.get("entity_name")]
        logger.info(f"📍 Sementes Semânticas recuperadas via Qdrant: {seeds}")
        return seeds

    async def identify_knowledge_gaps(self, namespace: str = "global") -> List[Dict[str, Any]]:
        """
        Identifica clusters isolados (ilhas) e sugere pontes tecnicas com granularidade controlada.
        """
        edges = self.graph_store.get_all_edges(namespace=namespace)
        if not edges:
            return []

        # 1. Detecta as ilhas de conhecimento (Componentes Conexos)
        # Por enquanto fazemos em Python, mas pronto para delegar ao Go modo 'find_islands'
        islands = self._find_islands(edges)
        
        # 2. Ordena ilhas por tamanho (maiores primeiro) para garantir pontes relevantes
        islands_sorted = sorted(islands, key=len, reverse=True)
        
        if len(islands_sorted) <= 1:
            return []

        gaps = []
        # 3. Tenta conectar as maiores ilhas (limite de 3 pontes para evitar custo excessivo)
        for i in range(min(3, len(islands_sorted) - 1)):
            island_a = islands_sorted[i]
            island_b = islands_sorted[i+1]
            
            # Pega exemplos reais de nos para injetar granularidade no prompt
            sample_a = list(island_a)[:5]
            sample_b = list(island_b)[:5]
            
            prompt = (
                f"Analise estes dois clusters de conhecimento tecnico no projeto '{namespace}':\n\n"
                f"Cluster A (Exemplos): {', '.join(sample_a)}\n"
                f"Cluster B (Exemplos): {', '.join(sample_b)}\n\n"
                f"Os nos existentes tem granularidade tecnica como: '{sample_a[0]}'.\n"
                "Tarefa: Sugira 1 unico conceito tecnico fundamental (com a MESMA granularidade) que funcione como uma 'Ponte' logica entre estes dois clusters.\n"
                "Responda apenas o nome do conceito em portugues, de forma concisa."
            )
            
            try:
                bridge_concept = await self.llm_engine.generate_answer(
                    messages=[
                        {"role": "system", "content": "Voce e um Arquiteto de Conhecimento especializado em unificar dominios fragmentados."},
                        {"role": "user", "content": prompt}
                    ]
                )
                
                # Limpeza básica da resposta
                bridge_concept = bridge_concept.strip(' ".\n').split('\n')[0]
                
                gaps.append({
                    "source_cluster": sample_a[0],
                    "target_cluster": sample_b[0],
                    "missing_link": bridge_concept,
                    "potential_impact": "Alta Densificacao Semantica"
                })
            except Exception as e:
                logger.error(f"Erro ao gerar ponte entre ilhas: {e}")
                
        return gaps

    def _find_islands(self, edges: List[tuple]) -> List[set]:
        """
        Algoritmo de Componentes Conexos para identificar ilhas de conhecimento.
        """
        adj = {}
        nodes = set()
        for u, _rel, v in edges:
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
            nodes.add(u)
            nodes.add(v)

        islands = []
        visited = set()
        
        for node in nodes:
            if node not in visited:
                # Nova ilha encontrada, inicia BFS
                current_island = set()
                queue = [node]
                visited.add(node)
                
                while queue:
                    curr = queue.pop(0)
                    current_island.add(curr)
                    for neighbor in adj.get(curr, []):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                
                islands.append(current_island)
        
        return islands

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    async def detect_document_type(self, sample_text: str) -> str:
        """
        Auto-descoberta ultrarrápida do domínio do documento.
        """
        if not sample_text or len(sample_text) < 10:
            return "Tecnologia e Negócios"
            
        system_prompt = (
            "Você é um Classificador de Documentos Ultrarrápido. "
            "Sua única função é ler as primeiras linhas de um arquivo e classificar o 'Domínio' dele em no máximo 3 palavras. "
            "Exemplos: 'Currículo Profissional', 'Contrato Jurídico', 'Relatório Financeiro', 'Prontuário Médico', 'Documentação de Software', 'Artigo Científico', 'Receita Culinária'."
            "Responda APENAS com o domínio, sem explicações."
        )
        
        # Pega os primeiros 1500 caracteres (mais que suficiente para inferir o domínio)
        snippet = sample_text[:1500]
        
        try:
            response = await self.llm_engine.generate_answer(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"TEXTO:\n{snippet}"}
                ],
                temperature=0.0
            )
            domain = response.strip(' "\'\n.').title()
            logger.info(f"🕵️ Domínio do Documento Detectado Automagicamente: {domain}")
            return domain
        except Exception as e:
            logger.warning(f"Falha ao detectar domínio (fallback para padrão): {e}")
            return "Tecnologia e Negócios"
