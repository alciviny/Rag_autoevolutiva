import logging
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tools.sourcing")

class StrategicSourcingTool(BaseTool):
    """
    Ferramenta de Logistica de Elite.
    Pesquisa componentes e gerencia a lista de compras do criador.
    """
    def __init__(self, orchestrator, graph_store):
        self.orchestrator = orchestrator
        self.graph = graph_store

    @property
    def name(self) -> str:
        return "search_and_source"

    @property
    def description(self) -> str:
        return (
            "Pesquisa preços e disponibilidade de componentes ou ferramentas na internet. "
            "Pode adicionar itens à lista de desejos (wishlist) do usuário."
        )

    async def execute(self, item_name: str, action: str = "search") -> str:
        """
        Action pode ser 'search' ou 'add_to_wishlist'.
        """
        try:
            if action == "search":
                prompt = f"Pesquise o preco medio e onde encontrar o componente '{item_name}' no Brasil. Seja direto e tecnico."
                res = await self.orchestrator.engineer.think(prompt)
                return f"Resultado da pesquisa para '{item_name}':\n{res}"
            
            elif action == "add_to_wishlist":
                # Adiciona ao Grafo como uma entidade tipo Wishlist
                from alana_system.preprocessing.entity_extractor import KnowledgeGraphSchema, EntitySchema
                new_graph = KnowledgeGraphSchema(
                    entities=[EntitySchema(name=item_name, type="Wishlist", description="Item aguardando compra.")],
                    relations=[]
                )
                self.graph.add_knowledge(new_graph, source_doc="manual_sourcing", page_number=0)
                return f"O item '{item_name}' foi adicionado à sua lista de desejos técnica."
                
            return "Ação não reconhecida."
                    
        except Exception as e:
            logger.error(f"Erro na StrategicSourcingTool: {e}")
            return f"Falha na logística: {str(e)}"
