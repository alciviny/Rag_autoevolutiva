import logging
from typing import Optional
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tools.delegation")

class DelegateTaskTool(BaseTool):
    name = "delegate_task"
    description = "Delega uma sub-missão para um especialista (ex: 'pesquisador', 'programador'). O resultado da sub-missão será retornado para você."
    
    def __init__(self, parent_engine):
        self.parent_engine = parent_engine

    async def execute(self, role: str, sub_mission: str) -> str:
        try:
            logger.info(f"🔄 DELEGANDO TAREFA para '{role}': {sub_mission}")
            
            from ..core.engine import AgentEngine
            
            memory_tool = self.parent_engine.registry.get_tool("query_memory")
            query_engine = memory_tool.query_engine if memory_tool else None
            
            # Instancia um Sub-agente (Worker) limpo
            worker = AgentEngine(
                llm=self.parent_engine.llm,
                query_engine=query_engine,
                is_primary=False  # Protege contra recursão infinita
            )
            worker.max_loops = 10
            
            # Dispara a sub_mission no mesmo namespace, para compartilhar o sandbox
            result = await worker.run_mission(
                f"Você é o Especialista '{role}'. Sua sub-missão é: {sub_mission}", 
                namespace=self.current_namespace
            )
            
            return f"[RESUMO DO ESPECIALISTA {role}]:\n{result}"
            
        except Exception as e:
            logger.error(f"Erro ao delegar tarefa para {role}: {e}")
            return f"[ERRO NA DELEGAÇÃO]: {str(e)}"
