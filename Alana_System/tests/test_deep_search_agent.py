import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from alana_system.qa_system.deep_search_agent import DeepSearchAgent
from alana_system.qa_system.searcher import WebSearcher
from alana_system.qa_system.storer import KnowledgeStorer
from alana_system.qa_system.crawler import WebCrawler
from alana_system.inference.llm_engine import LLMEngine
from alana_system.memory.graph_store import GraphStore
from alana_system.preprocessing.entity_extractor import EntityExtractor, KnowledgeGraphSchema

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate_answer = AsyncMock(return_value="Relatorio Gerado")
    return llm

@pytest.fixture
def mock_graph_store():
    store = MagicMock()
    return store

@pytest.fixture
def mock_extractor():
    extractor = MagicMock()
    schema = KnowledgeGraphSchema(entities=[], relations=[])
    extractor.extract_graph = AsyncMock(return_value=schema)
    return extractor

@pytest.mark.asyncio
async def test_deep_search_agent_perform(mock_llm, mock_graph_store, mock_extractor):
    agent = DeepSearchAgent(mock_llm, mock_graph_store, mock_extractor)
    
    # Mock searcher.search
    agent.searcher.search = AsyncMock(return_value=[
        {"url": "http://test.com", "title": "Test Title", "content": "Test Content", "score": 0.9}
    ])
    agent.searcher.deep_scrape = AsyncMock(return_value="Scraped Content")
    
    res = await agent.perform_deep_search("test query", namespace="test_ns", use_deep_crawl=False)
    
    assert res["status"] == "completed"
    assert res["query"] == "test query"
    assert res["namespace"] == "test_ns"
    assert res["report"] == "Relatorio Gerado"
    assert res["sources"] == ["http://test.com"]
    assert res["stored_in_graph"] is True

@pytest.mark.asyncio
async def test_deep_search_agent_no_results(mock_llm, mock_graph_store, mock_extractor):
    agent = DeepSearchAgent(mock_llm, mock_graph_store, mock_extractor)
    agent.searcher.search = AsyncMock(return_value=[])
    
    res = await agent.perform_deep_search("test query")
    assert res["status"] == "no_results"

@pytest.mark.asyncio
async def test_knowledge_storer(mock_graph_store, mock_extractor):
    storer = KnowledgeStorer(mock_graph_store, mock_extractor)
    success = await storer.store_report("query", "report content", namespace="test_ns")
    assert success is True
    mock_extractor.extract_graph.assert_called_once_with("report content")
    mock_graph_store.add_knowledge.assert_called_once()

@pytest.mark.asyncio
async def test_web_searcher():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"url": "http://test.com", "title": "Test Title", "content": "Test Content", "score": 0.9}
        ]
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=mock_response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=None)
    with patch("alana_system.qa_system.searcher.httpx.AsyncClient", return_value=context):
        searcher = WebSearcher(api_key="fake-key")
        results = await searcher.search("query")
        assert len(results) == 1
        assert results[0]["url"] == "http://test.com"

@pytest.mark.asyncio
async def test_web_crawler():
    crawler = WebCrawler()
    with patch.object(crawler, "_is_public_url", return_value=True), patch.object(crawler, "_scrape_page") as mock_scrape:
        mock_scrape.return_value = {
            "text": "Extracted Text Content",
            "links": []
        }
        text = await crawler.crawl("http://start.com")
        assert text == "Extracted Text Content"
