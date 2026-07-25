import logging
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tools.evolution")

class PromoteTool(BaseTool):
    """
    A Ferramenta de Evolução.
    Permite promover uma ferramenta validada de um namespace local para o namespace global.
    """
    def __init__(self, dynamic_manager):
        self.manager = dynamic_manager
        self.current_namespace = "global"

    @property
    def name(self) -> str:
        return "promote_to_global"

    @property
    def description(self) -> str:
        return "Eleva uma ferramenta de um namespace local para o nível GLOBAL, tornando-a disponível para todos os projetos."

    async def execute(self, tool_name: str) -> str:
        """
        Promove a ferramenta do namespace atual para o global.
        """
        if self.current_namespace == "global":
            return "[ERRO] Você já está no namespace global. Não há para onde promover."
            
        success, msg = self.manager.promote_tool(self.current_namespace, tool_name)
        
        if success:
            return f"[SUCESSO] Ferramenta '{tool_name}' promovida para GLOBAL com sucesso."
        else:
            return f"[FALHA] Não foi possível promover a ferramenta: {msg}"
