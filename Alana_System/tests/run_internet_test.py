import sys
import os
from pathlib import Path
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Adiciona a raiz ao PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alana_system.qa_system.deep_search_agent import DeepSearchAgent
from alana_system.inference.llm_engine import LLMEngine
from alana_system.memory.graph_store import GraphStore
from alana_system.preprocessing.entity_extractor import EntityExtractor

async def example_search():
    llm = LLMEngine()
    graph = GraphStore("data/test_graph.db")
    extractor = EntityExtractor(llm)
    agent = DeepSearchAgent(llm, graph, extractor)
    result = await agent.perform_deep_search("Como funciona o protocolo MQTT no IoT industrial?")
    print("Relatório:")
    print(result.get("report"))

if __name__ == "__main__":
    asyncio.run(example_search())
