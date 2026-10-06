import logging
from .base_tool import BaseTool
from ...memory.graph_store import GraphStore

logger = logging.getLogger("alana.agent.tools.store_fact")

class StoreFactTool(BaseTool):
    name = "store_fact"
    description = "Salva uma descoberta tecnica permanentemente no Grafo de Conhecimento. Argumentos: 'subject' (sujeito), 'relation' (verbo/relacao), 'object_name' (objeto)."
    
    def __init__(self, graph_store: GraphStore, intelligence=None):
        self.graph_store = graph_store
        self.intelligence = intelligence
        
    async def execute(self, subject: str, relation: str, object_name: str = None, object: str = None) -> str:
        if not self.graph_store:
            return "Erro: Base de grafos nao disponivel."
            
        object_name = object_name or object
        
        if not all([subject, relation, object_name]):
            return "[ERRO] StoreFactTool exige: 'subject', 'relation' e 'object_name'."
            
        try:
            if self.intelligence:
                subject = await self.intelligence.reconcile_entity(subject, self.current_namespace)
                object_name = await self.intelligence.reconcile_entity(object_name, self.current_namespace)
            # Salva o fato respeitando o namespace do projeto atual
            success = self.graph_store.add_fact(
                subject, relation, object_name, 
                source="AGENT_DISCOVERY",
                namespace=self.current_namespace
            )
            
            if success:
                return f"✅ FATO REGISTRADO no projeto '{self.current_namespace}': {subject} --[{relation}]--> {object_name}."
            else:
                return "Falha ao persistir fato no banco de dados."
        except Exception as e:
            logger.error(f"Erro na StoreFactTool: {e}")
            return f"[ERRO]: {str(e)}"
