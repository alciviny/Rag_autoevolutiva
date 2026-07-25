import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Garante que o src est\u00e1 no path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from alana_system.agent.core.engine import AgentEngine
from alana_system.agent.tools.analyst_tool import AutonomousAnalystTool
from alana_system.agent.tools.theory_tool import TheoryValidationTool
from alana_system.agent.tools.research_tool import ResearchTool
from alana_system.agent.tools.memory_tool import MemoryTool

# Mock global para evitar carregar modelos reais durante testes unitários
patch('alana_system.inference.llm_engine.LLMEngine').start()
patch('alana_system.embeddings.embedder.TextEmbedder').start()

class TestAgentSystem(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        # Mocks de depend\u00eancias
        self.mock_llm = MagicMock()
        self.mock_store = MagicMock()
        self.mock_intelligence = MagicMock()
        self.mock_intelligence.graph_store = self.mock_store
        self.mock_query_engine = MagicMock()
        self.mock_search_agent = MagicMock()
        
    def test_engine_initialization(self):
        """Verifica se o AgentEngine carrega todas as ferramentas corretamente."""
        engine = AgentEngine(
            query_engine=self.mock_query_engine,
            deep_search_agent=self.mock_search_agent,
            graph_intelligence=self.mock_intelligence
        )
        
        # Verifica se as ferramentas essenciais estão registradas
        tools = engine.registry.list_tools()
        self.assertIn("write_code", tools)
        self.assertIn("python_runner", tools)
        self.assertIn("consult_memory", tools)
        self.assertIn("research", tools)
        self.assertIn("autonomous_analyst", tools)
        self.assertIn("validate_theory", tools)
        
    async def test_analyst_tool_execution(self):
        """Testa se a ferramenta de analista chama os métodos corretos da inteligência."""
        tool = AutonomousAnalystTool(self.mock_intelligence)
        
        from unittest.mock import AsyncMock
        self.mock_intelligence.analyze_patterns = AsyncMock(return_value={
            "status": "success",
            "insights": ["Padr\u00e3o X detectado"],
            "authorities": [("Node1", 0.5)],
            "clusters_count": 2
        })
        
        result = await tool.execute(mode="patterns")
        self.assertIn("RELATÓRIO DE AUDITORIA", result)
        self.mock_intelligence.analyze_patterns.assert_called_once()

    async def test_theory_validation_logic(self):
        """Testa o fluxo da ferramenta de validação de teoria."""
        tool = TheoryValidationTool()
        
        # Mock dos componentes internos
        from unittest.mock import AsyncMock
        tool.writer = MagicMock()
        tool.runner = MagicMock()
        tool.writer.execute = AsyncMock(return_value="OK")
        tool.runner.execute = AsyncMock(return_value="Simulação rodou OK")
        
        result = await tool.execute(
            theory="A gravidade existe",
            simulation_code="print('Gravidade OK')"
        )
        
        self.assertIn("PROTOCOLO DE VALIDAÇÃO CIENTÍFICA", result)
        self.assertIn("Simulação rodou OK", result)
        # Verifica se injetou o helper
        tool.writer.execute.assert_called_once()
        saved_code = tool.writer.execute.call_args[0][1]
        self.assertIn("import alana_lab", saved_code)

    def test_research_tool_dependency_injection(self):
        """Verifica se a ResearchTool n\u00e3o quebra com inje\u00e7\u00e3o de depend\u00eancia."""
        tool = ResearchTool(self.mock_search_agent)
        self.assertEqual(tool.agent, self.mock_search_agent)

if __name__ == "__main__":
    unittest.main()
