import asyncio
import logging
from typing import Set, Dict, Any
from datetime import datetime
from alana_system.utils.background_tasks import task_manager

logger = logging.getLogger("alana.core.discovery")

class DiscoveryManager:
    """
    Motor de Curiosidade Autonoma.
    Decide quando a Alana deve pesquisar algo novo que ela viu.
    """
    def __init__(self, orchestrator, graph_store, sensory_manager):
        self.orchestrator = orchestrator
        self.graph = graph_store
        self.sensory = sensory_manager
        self.research_queue: Set[str] = set() 
        self.already_researched: Set[str] = set()
        self.semaphore = asyncio.Semaphore(2)

    async def evaluate_discovery(self, entities: list, namespace: str = "global"):
        """Avalia se alguma das entidades vistas precisa de pesquisa autonoma."""
        for entity in entities:
            name = entity.name
            if name in self.research_queue or name in self.already_researched:
                continue
            
            entity_data = self.graph.get_entity(name, namespace)
            
            is_unknown = not entity_data or not entity_data["description"] or len(entity_data["description"]) < 30
            
            if is_unknown:
                logger.info(f"🔍 Curiosidade: Iniciando pesquisa sobre '{name}'...")
                self.research_queue.add(name)
                task_manager.run_task(
                    self.perform_autonomous_research, 
                    name, 
                    namespace, 
                    name=f"autonomous_research_{name}", 
                    namespace=namespace
                )

    async def perform_autonomous_research(self, entity_name: str, namespace: str):
        """Pesquisa em background com controle de concorrência."""
        async with self.semaphore:
            try:
                prompt = f"Realize uma pesquisa técnica profunda sobre '{entity_name}'. Descubra utilidade e especificações. Resuma para o Grafo."
                result = await self.orchestrator.engineer.think(prompt)
                
                from alana_system.preprocessing.entity_extractor import KnowledgeGraphSchema, EntitySchema
                new_graph = KnowledgeGraphSchema(
                    entities=[EntitySchema(name=entity_name, type="Pesquisa Autonoma", description=result)],
                    relations=[]
                )
                intelligence = getattr(getattr(self.orchestrator, "query_engine", None), "intelligence", None)
                if intelligence:
                    await intelligence.reconcile_graph(new_graph, namespace)
                self.graph.add_knowledge(new_graph, source_doc="autonomous_discovery", page_number=0, namespace=namespace)
                await self.sensory.broadcast_alert(f"Concluí minha pesquisa sobre '{entity_name}'.", namespace)
                self.already_researched.add(entity_name)
            except Exception as e:
                logger.error(f"Erro na pesquisa de {entity_name}: {e}")
            finally:
                self.research_queue.discard(entity_name)
