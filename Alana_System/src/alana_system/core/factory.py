import os
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

logger = logging.getLogger("alana.core.factory")

class AlanaContainer:
    """
    Fábrica Industrial de Motores (Dependency Injection Container).
    Gerencia o ciclo de vida e a instanciação de todos os componentes da Alana.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AlanaContainer, cls).__new__(cls)
            cls._instance.engines: Dict[str, Any] = {}
        return cls._instance

    def initialize_all(self):
        """Inicializa todos os motores em ordem de dependência."""
        logger.info("🛠️ AlanaContainer: Iniciando montagem dos motores...")
        
        # 1. Core Engines (Independents)
        from alana_system.inference.llm_engine import LLMEngine
        from alana_system.embeddings.embedder import TextEmbedder
        from alana_system.memory.graph_store import GraphStore
        from alana_system.core.sensory import SensoryManager
        from alana_system.ingestion.audio_transcriber import AudioTranscriber
        
        self.engines["llm_engine"] = LLMEngine()
        self.engines["embedder"] = TextEmbedder()
        self.engines["graph_store"] = GraphStore()
        self.engines["sensory_manager"] = SensoryManager()
        self.engines["shared_transcriber"] = AudioTranscriber(model_size="base")

        # 2. Storage Layer
        from alana_system.memory.vector_store import VectorStore
        from alana_system.memory.experience_store import ExperienceStore
        
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        try:
            self.engines["vector_store"] = VectorStore(collection_name="alana_knowledge_base", host=qdrant_host)
            self.engines["entity_vector_store"] = VectorStore(collection_name="alana_entities", client=self.engines["vector_store"].client, vector_dim=self.engines["embedder"].model.get_sentence_embedding_dimension())
            logger.info(f"✅ Conectado ao Qdrant em {qdrant_host}")
        except Exception as e:
            logger.warning(f"⚠️ Qdrant falhou: {e}. Usando modo local.")
            os.makedirs("data/memory/qdrant_local", exist_ok=True)
            self.engines["vector_store"] = VectorStore(collection_name="alana_knowledge_base", path="data/memory/qdrant_local")
            self.engines["entity_vector_store"] = VectorStore(collection_name="alana_entities", client=self.engines["vector_store"].client, vector_dim=self.engines["embedder"].model.get_sentence_embedding_dimension())
            
        self.engines["experience_store"] = ExperienceStore(
            vector_store=self.engines["vector_store"], 
            embedder=self.engines["embedder"]
        )

        # 3. Intelligence Layer
        from alana_system.query.query_engine import QueryEngine
        from alana_system.preprocessing.entity_extractor import EntityExtractor
        from alana_system.memory.intelligence import GraphIntelligence
        from alana_system.core.workflow_manager import WorkflowManager
        
        self.engines["graph_intelligence"] = GraphIntelligence(
            graph_store=self.engines["graph_store"], 
            vector_store=self.engines["vector_store"], 
            llm_engine=self.engines["llm_engine"], 
            embedder=self.engines["embedder"],
            entity_vector_store=self.engines["entity_vector_store"]
        )

        self.engines["query_engine"] = QueryEngine(
            vector_store=self.engines["vector_store"],
            embedder=self.engines["embedder"],
            graph_store=self.engines["graph_store"],
            llm_engine=self.engines["llm_engine"],
            graph_intelligence=self.engines["graph_intelligence"]
        )
        
        self.engines["entity_extractor"] = EntityExtractor(llm=self.engines["llm_engine"])
        self.engines["workflow_manager"] = WorkflowManager(graph_store=self.engines["graph_store"])

        # 4. Agent Layer
        from alana_system.qa_system.deep_search_agent import DeepSearchAgent
        from alana_system.agent.orchestrator import MultiAgentOrchestrator
        from alana_system.core.discovery import DiscoveryManager
        
        self.engines["deep_search_agent"] = DeepSearchAgent(
            llm_engine=self.engines["llm_engine"],
            graph_store=self.engines["graph_store"],
            entity_extractor=self.engines["entity_extractor"],
            graph_intelligence=self.engines["graph_intelligence"],
        )
        
        self.engines["orchestrator"] = MultiAgentOrchestrator(
            llm_engine=self.engines["llm_engine"],
            query_engine=self.engines["query_engine"],
            deep_search_agent=self.engines["deep_search_agent"],
            experience_store=self.engines["experience_store"]
        )
        
        self.engines["discovery_manager"] = DiscoveryManager(
            orchestrator=self.engines["orchestrator"],
            graph_store=self.engines["graph_store"],
            sensory_manager=self.engines["sensory_manager"]
        )

        # 5. Specialized Tools Registry
        from alana_system.agent.tools.catalyst_tool import KnowledgeCatalystTool
        from alana_system.agent.tools.alert_tool import AlertUserTool
        from alana_system.agent.tools.spatial_tool import SpatialLocatorTool
        from alana_system.agent.tools.telemetry_tool import TelemetryQueryTool
        from alana_system.agent.tools.sourcing_tool import StrategicSourcingTool
        from alana_system.agent.tools.evolution_tool import PromoteTool
        
        orch = self.engines["orchestrator"]
        self.engines["vision_processor"] = orch.engineer.registry.get_tool("analyze_visual_data").vision
        orch.engineer.registry.register(KnowledgeCatalystTool(intelligence=self.engines["graph_intelligence"]))
        orch.engineer.registry.register(AlertUserTool(sensory_manager=self.engines["sensory_manager"]))
        orch.engineer.registry.register(SpatialLocatorTool(graph_store=self.engines["graph_store"]))
        orch.engineer.registry.register(TelemetryQueryTool(graph_store=self.engines["graph_store"]))
        orch.engineer.registry.register(StrategicSourcingTool(orchestrator=orch, graph_store=self.engines["graph_store"]))
        orch.engineer.registry.register(PromoteTool(dynamic_manager=orch.engineer.dynamic_manager))

        # 6. Intent & Final Wrap
        from alana_system.core.intent_manager import IntentManager
        self.engines["intent_manager"] = IntentManager(self)

        logger.info("🚀 AlanaContainer: Montagem concluída com sucesso.")

    def get(self, name: str) -> Any:
        return self.engines.get(name)

    # Implementação de __getitem__ para compatibilidade com o IntentManager que espera um objeto similar a app.state
    def __getitem__(self, key):
        return self.engines.get(key)
    
    def __getattr__(self, name):
        if name in self.engines:
            return self.engines[name]
        raise AttributeError(f"'AlanaContainer' object has no attribute '{name}'")

# Singleton Global
container = AlanaContainer()
