import logging
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tools.spatial")

class SpatialLocatorTool(BaseTool):
    """
    Ferramenta de Memoria Espacial.
    Permite que o agente localize objetos e ferramentas no ambiente 
    baseando-se no historico visual (last_location).
    """
    def __init__(self, graph_store):
        self.graph = graph_store

    @property
    def name(self) -> str:
        return "locate_object"

    @property
    def description(self) -> str:
        return (
            "Localiza objetos, ferramentas ou componentes no laboratório. "
            "Informe o nome do objeto e eu direi onde ele foi visto pela última vez."
        )

    async def execute(self, object_name: str) -> str:
        """
        Consulta o Grafo para encontrar a localizacao.
        """
        try:
            # Consulta SQL direta para agilidade (Industrial)
            query = """
                SELECT name, last_location, last_seen 
                FROM entities 
                WHERE namespace = ? AND (name LIKE ? OR description LIKE ?)
                ORDER BY last_seen DESC LIMIT 1
            """
            params = (self.current_namespace, f"%{object_name}%", f"%{object_name}%")
            
            with self.graph._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                row = cursor.fetchone()
                
                if row and row["last_location"] != "unknown":
                    return f"O objeto '{row['name']}' foi visto pela última vez na localização '{row['last_location']}' em {row['last_seen']}."
                elif row:
                    return f"Encontrei '{row['name']}' no registro, mas ainda não mapeei sua localização física."
                else:
                    return f"Não encontrei registros de localização para '{object_name}' no meu banco de dados atual."
                    
        except Exception as e:
            logger.error(f"Erro na SpatialLocatorTool: {e}")
            return f"Falha ao tentar localizar objeto: {str(e)}"
