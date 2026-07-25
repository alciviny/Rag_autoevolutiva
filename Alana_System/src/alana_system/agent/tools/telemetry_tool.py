import logging
from typing import Optional
from .base_tool import BaseTool

logger = logging.getLogger("alana.agent.tools.telemetry")

class TelemetryQueryTool(BaseTool):
    """
    Ferramenta de Analise de Dados Tecnicos.
    Permite ao agente consultar historicos de medicoes (voltagem, pressao, etc)
    registrados pelo Lab Assistant.
    """
    def __init__(self, graph_store):
        self.graph = graph_store

    @property
    def name(self) -> str:
        return "query_telemetry"

    @property
    def description(self) -> str:
        return (
            "Consulta o histórico de medições técnicas capturadas. "
            "Pode ser usado para saber o último valor de um sensor, a média de leituras ou tendências."
        )

    async def execute(self, entity_name: str, limit: int = 5) -> str:
        """
        Consulta os ultimos logs de um equipamento/sensor.
        """
        try:
            query = """
                SELECT value, unit, raw_reading, timestamp 
                FROM telemetry 
                WHERE entity_name LIKE ? 
                ORDER BY timestamp DESC LIMIT ?
            """
            params = (f"%{entity_name}%", limit)
            
            with self.graph._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                if not rows:
                    return f"Não encontrei registros de telemetria para '{entity_name}'."
                
                res = [f"Histórico de '{entity_name}':"]
                for r in rows:
                    res.append(f"- {r['timestamp']}: {r['raw_reading']} (Valor: {r['value']} {r['unit']})")
                
                return "\n".join(res)
                    
        except Exception as e:
            logger.error(f"Erro na TelemetryQueryTool: {e}")
            return f"Falha ao organizar telemetria: {str(e)}"
