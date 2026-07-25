import logging
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tools.alert")

class AlertUserTool(BaseTool):
    """
    Ferramenta de Proatividade Industrial.
    Permite que o agente envie mensagens de voz ou alertas visuais 
    para os dispositivos externos do usuário (wearables/IoT).
    """
    def __init__(self, sensory_manager):
        self.sensory = sensory_manager

    @property
    def name(self) -> str:
        return "alert_user"

    @property
    def description(self) -> str:
        return (
            "Envia uma mensagem de voz ou alerta imediato para os dispositivos externos (wearables) do usuário. "
            "Use para informar sobre conclusões de tarefas, alertas de segurança ou informações urgentes."
        )

    async def execute(self, message: str) -> str:
        """
        Executa o broadcast proativo.
        """
        try:
            await self.sensory.broadcast_alert(message)
            return f"Alerta enviado com sucesso: '{message}'"
        except Exception as e:
            logger.error(f"Erro ao executar alert_user: {e}")
            return f"Falha ao enviar alerta: {str(e)}"
