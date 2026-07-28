import logging
from .base_tool import BaseTool
from ...memory.intelligence import GraphIntelligence

logger = logging.getLogger(__name__)

class NavigateGraphTool(BaseTool):
    name = "navigate_graph"
    description = "Navega pelas conexões lógicas do Grafo de Conhecimento. Use para descobrir relações entre componentes ou conceitos técnicos. Argumentos: 'entity' (nome do nó), 'hops' (número de saltos, padrão 1)."
    
    def __init__(self, intelligence: GraphIntelligence):
        self.intelligence = intelligence
        
    async def execute(self, entity: str, hops: int = 1) -> str:
        if not self.intelligence:
            return "Erro: Módulo de inteligência de grafo não inicializado."
            
        try:
            # Garante que hops seja int
            hops = int(hops)
            ns = getattr(self, "current_namespace", "global")
            
            # Tenta encontrar o nó mais próximo usando Similaridade Vetorial (Qdrant)
            closest_seeds = await self.intelligence.get_seed_entities(entity, top_k=1, namespace=ns)
            
            if closest_seeds:
                best_match = closest_seeds[0]
                result = self.intelligence.get_neighborhood(best_match, hops, namespace=ns)
                
                if best_match.lower() != entity.lower():
                    return f"[GRAFO]: Explorando vizinhança de '{best_match}' (match semântico para '{entity}')\n{result}"
                else:
                    return f"[GRAFO]: Explorando vizinhança de '{best_match}'\n{result}"
            else:
                # Fallback exato
                result = self.intelligence.get_neighborhood(entity, hops, namespace=ns)
                return f"[GRAFO]: Explorando vizinhança de '{entity}'\n{result}"
                
        except Exception as e:
            logger.error(f"Erro na NavigateGraphTool: {e}")
            return f"[ERRO DE NAVEGAÇÃO]: {str(e)}"
