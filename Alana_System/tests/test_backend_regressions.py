import sqlite3
import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from alana_system.memory.graph_store import GraphStore
from alana_system.memory.vector_store import VectorStore
from alana_system.preprocessing.entity_extractor import KnowledgeGraphSchema
from alana_system.ingestion.manager import IngestionManager
from alana_system.ingestion.text_extractor import PageText
from alana_system.agent.core.dynamic_manager import DynamicToolManager
from alana_system.agent.core.tool_registry import ToolRegistry
from alana_system.agent.tools.base_tool import BaseTool
from alana_system.agent.tools.store_fact_tool import StoreFactTool
from alana_system.agent.tools.path_utils import safe_workspace_file
from alana_system.ingestion.cleaner import CleanedPageText
from alana_system.preprocessing.chunker import TextChunker
from alana_system.preprocessing.entity_extractor import EntityExtractor
from alana_system.memory.intelligence import GraphIntelligence
from alana_system.agent.tools.telemetry_tool import TelemetryQueryTool
from alana_system.agent.tools.spatial_tool import SpatialLocatorTool
from alana_system.core.sensory import SensoryManager


class GraphStoreRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "graph.db"
        self.store = GraphStore(str(self.db))

    def tearDown(self):
        self.temp.cleanup()

    def test_facts_and_aliases_are_namespace_scoped(self):
        self.store.add_fact("Ana", "knows", "Beto", namespace="team-a")
        self.store.add_fact("Carla", "knows", "Davi", namespace="team-b")
        self.store.add_alias("Aninha", "Ana", namespace="team-a")
        self.store.add_fact("Aninha", "knows", "Eva", namespace="team-a")

        self.assertEqual(self.store.get_all_edges("team-a"), [("Ana", "knows", "Beto"), ("Ana", "knows", "Eva")])
        self.assertEqual(self.store.get_all_edges("team-b"), [("Carla", "knows", "Davi")])
        self.assertEqual(self.store.get_all_edges("global"), [])
        with self.assertRaises(ValueError):
            self.store.add_alias("Other", "Ana", namespace="team-b")

    def test_legacy_alias_migration_keeps_aliases_in_global(self):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("INSERT INTO entities (name, type, namespace) VALUES ('Canonical', 'Thing', 'global')")
            conn.execute("DROP TABLE entity_aliases")
            conn.execute("CREATE TABLE entity_aliases (alias TEXT PRIMARY KEY, canonical_name TEXT NOT NULL)")
            conn.execute("INSERT INTO entity_aliases VALUES ('Old Name', 'Canonical')")
            conn.commit()
        finally:
            conn.close()
        migrated = GraphStore(str(self.db))
        self.assertEqual(migrated._resolve_canonical_name_cached("Old Name", "global"), "Canonical")
        self.assertEqual(migrated._resolve_canonical_name_cached("Old Name", "team-a"), "Old Name")

    def test_failed_write_rolls_back_and_propagates(self):
        broken_graph = KnowledgeGraphSchema(entities=[{"name": "A", "type": "Thing"}], relations=[])
        with self.store._connect() as conn:
            conn.execute("CREATE TRIGGER reject_entity BEFORE INSERT ON entities BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(Exception):
            self.store.add_knowledge(broken_graph, "broken", 1, namespace="tenant")
        self.assertEqual(self.store.count_entities(), 0)

    def test_subgraph_finds_two_hops_and_filters_tenant(self):
        for a, b in [("A", "B"), ("B", "C"), ("C", "D")]:
            self.store.add_fact(a, "links", b, namespace="tenant")
        self.store.add_fact("A", "links", "Secret", namespace="other")
        results = self.store.query_subgraph(["A"], namespace="tenant")
        pairs = {(r["subject"], r["object"]) for r in results}
        self.assertEqual(pairs, {("A", "B"), ("B", "C")})

    def test_telemetry_and_location_queries_do_not_cross_namespaces(self):
        self.store.add_telemetry_reading("Pump", 10, "V", "10 V", "tenant-a")
        self.store.add_telemetry_reading("Pump", 20, "V", "20 V", "tenant-b")
        self.store.add_knowledge(KnowledgeGraphSchema(entities=[{"name": "Pump", "type": "Device", "description": ""}], relations=[]), "a", 1, "tenant-a", {"location": "Room A"})
        telemetry = TelemetryQueryTool(self.store)
        telemetry.set_context("tenant-a")
        location = SpatialLocatorTool(self.store)
        location.set_context("tenant-a")
        self.assertIn("10 V", asyncio.run(telemetry.execute("Pump")))
        self.assertNotIn("20 V", asyncio.run(telemetry.execute("Pump")))
        self.assertIn("Room A", asyncio.run(location.execute("Pump")))
        location.set_context("tenant-b")
        self.assertNotIn("Room A", asyncio.run(location.execute("Pump")))

    def test_recent_telemetry_is_namespace_scoped_and_newest_first(self):
        self.store.add_telemetry_reading("Pump", 10, "V", "10 V", "tenant-a")
        self.store.add_telemetry_reading("Pump", 20, "V", "20 V", "tenant-a")
        self.store.add_telemetry_reading("Secret", 99, "V", "99 V", "tenant-b")
        rows = self.store.get_recent_telemetry("tenant-a", limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["raw_reading"], "20 V")


class VectorStoreRegressionTests(unittest.TestCase):
    def test_upserts_are_tenant_scoped_and_do_not_mutate_filter(self):
        from qdrant_client import QdrantClient
        from alana_system.memory.vector_store import EmbeddedChunk
        client = QdrantClient(location=":memory:")
        store = VectorStore("test", vector_dim=2, client=client)
        chunk = lambda text: EmbeddedChunk(chunk_id="same", source_name="doc", page_number=1, text=text, embedding=[1.0, 0.0])
        store.upsert_embeddings([chunk("A")], namespace="a")
        store.upsert_embeddings([chunk("B")], namespace="b")
        self.assertEqual(store.count(), 2)

        original_filter = Filter(must=[FieldCondition(key="file_name", match=MatchValue(value="doc"))])
        store.search(__import__("numpy").array([1.0, 0.0]), namespace="a", filters=original_filter)
        self.assertEqual(len(original_filter.must), 1)
        client.close()


class IngestionBatchRegressionTests(unittest.TestCase):
    def test_long_pages_are_split_with_bounded_overlap(self):
        manager = IngestionManager.__new__(IngestionManager)
        manager.llm_batch_size = 10
        manager.llm_batch_overlap = 3
        source = "abcdefghijklmnopqrstuv"
        batches = manager._prepare_extraction_batches(
            [PageText(page_number=7, text=source, char_count=len(source))], "long.txt"
        )
        self.assertTrue(batches)
        self.assertTrue(all(0 < len(text) <= 10 for text, _, _ in batches))
        self.assertTrue(all(page == 7 for _, page, _ in batches))
        self.assertEqual([number for _, _, number in batches], list(range(1, len(batches) + 1)))
        self.assertEqual(batches[0][0], "abcdefghij")

    def test_extraction_batches_never_merge_source_pages(self):
        manager = IngestionManager.__new__(IngestionManager)
        manager.llm_batch_size = 100
        manager.llm_batch_overlap = 10
        pages = [
            PageText(page_number=1, text="source one", char_count=10),
            PageText(page_number=2, text="source two", char_count=10),
        ]
        batches = manager._prepare_extraction_batches(pages, "manual.pdf")
        self.assertEqual([(page, text) for text, page, _ in batches], [(1, "source one"), (2, "source two")])


class AgentToolRegressionTests(unittest.TestCase):
    def test_tool_schema_describes_fact_arguments(self):
        registry = ToolRegistry()
        registry.register(StoreFactTool(Mock()))
        function = registry.get_openai_tools_schema()[0]["function"]
        self.assertEqual(set(function["parameters"]["properties"]), {"subject", "relation", "object_name", "object"})
        self.assertEqual(set(function["parameters"]["required"]), {"subject", "relation"})

    def test_dynamic_tools_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            manager = DynamicToolManager(root)
            self.assertFalse(manager.save_tool("tenant", "../escape", "class X: pass")[0])
            with self.assertRaises(ValueError):
                manager._get_namespace_path("../outside")

    def test_dynamic_tools_require_one_async_tool_with_matching_name(self):
        code = '''from alana_system.agent.tools.base_tool import BaseTool
class safe_tool(BaseTool):
    @property
    def name(self): return "safe_tool"
    @property
    def description(self): return "safe"
    async def execute(self): return "ok"
'''
        with tempfile.TemporaryDirectory() as root:
            manager = DynamicToolManager(root)
            self.assertTrue(manager.save_tool("tenant", "safe_tool", code)[0])
            tools = manager.load_tools_for_namespace("tenant")
            self.assertEqual([tool.name for tool in tools], ["safe_tool"])

    def test_workspace_paths_reject_absolute_and_parent_traversal(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            for filename in ("../outside/secret", str(Path(outside) / "secret")):
                with self.assertRaises(PermissionError):
                    safe_workspace_file(Path(root), "tenant-a", filename)

    def test_unisolated_code_runners_are_disabled_by_default(self):
        import os
        from unittest.mock import patch
        from alana_system.agent.tools.code_runners.python_runner import PythonRunnerTool
        with patch.dict(os.environ, {}, clear=True):
            result = asyncio.run(PythonRunnerTool().execute("anything.py"))
        self.assertIn("worker isolado", result)

    def test_background_task_receives_namespace(self):
        from alana_system.utils.background_tasks import BackgroundTaskManager, TaskStatus
        manager = BackgroundTaskManager()
        manager.tasks.clear()
        seen = []

        async def job(label, namespace):
            seen.append((label, namespace))

        async def wait_for_completion():
            task_id = manager.run_task(job, "positional", name="namespace-regression", namespace="tenant-a", max_retries=0)
            for _ in range(50):
                if manager.tasks[task_id].status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    return task_id
                await asyncio.sleep(0.01)
        task_id = asyncio.run(wait_for_completion())
        self.assertEqual(seen, [("positional", "tenant-a")])
        self.assertEqual(manager.get_task_status(task_id)["status"], "COMPLETED")

    def test_agent_websocket_starts_one_mission_and_rejects_invalid_input(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from alana_system.api.routes.agent import router

        class Orchestrator:
            def __init__(self): self.calls = []
            async def run_complex_mission(self, mission, namespace, callback):
                self.calls.append((mission, namespace))
                await callback("started", {"ok": True})

        app = FastAPI()
        app.include_router(router)
        app.state.orchestrator = Orchestrator()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/agent") as websocket:
                websocket.send_text("not json")
                self.assertEqual(websocket.receive_json()["type"], "error")
                websocket.send_json({"mission": "test", "namespace": "tenant-a"})
                self.assertEqual(websocket.receive_json()["type"], "started")
        self.assertEqual(app.state.orchestrator.calls, [("test", "tenant-a")])

    def test_agent_websocket_aborts_active_mission(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from alana_system.api.routes.agent import router

        class Orchestrator:
            def __init__(self): self.cancelled = False
            async def run_complex_mission(self, mission, namespace, callback):
                try:
                    await callback("started", {})
                    await asyncio.sleep(30)
                finally:
                    self.cancelled = True

        app = FastAPI()
        app.include_router(router)
        app.state.orchestrator = Orchestrator()
        with TestClient(app) as client:
            with client.websocket_connect("/ws/agent") as websocket:
                websocket.send_json({"mission": "long"})
                self.assertEqual(websocket.receive_json()["type"], "started")
                websocket.send_json({"action": "abort"})
                self.assertEqual(websocket.receive_json()["type"], "mission_cancelled")
        self.assertTrue(app.state.orchestrator.cancelled)


class _TestTool(BaseTool):
    @property
    def name(self): return "test"
    @property
    def description(self): return "test"
    async def execute(self, value: str): return value


class AdditionalRegressionTests(unittest.TestCase):
    def test_health_endpoint_uses_supported_llm_model_attributes(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from alana_system.api.dependencies import get_graph_store, get_llm_engine, get_vector_store
        from alana_system.api.routes.admin import router
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_llm_engine] = lambda: SimpleNamespace(local_model="local-model")
        app.dependency_overrides[get_vector_store] = lambda: object()
        app.dependency_overrides[get_graph_store] = lambda: object()
        with TestClient(app) as client:
            result = client.get("/api/health")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["model"], "local-model")

    def test_chunker_falls_back_to_python_when_go_fails(self):
        chunker = TextChunker(max_chars=100, overlap_chars=10, min_chars=20)
        chunker.bridge.call = Mock(side_effect=RuntimeError("missing executable"))
        page = CleanedPageText(page_number=1, text="technical " * 40, original_char_count=440, cleaned_char_count=440)
        chunks = chunker.chunk_pages([page], "source.txt")
        self.assertGreater(len(chunks), 0)
        self.assertTrue(all(len(chunk.text) <= 100 for chunk in chunks))

    def test_llm_failure_text_is_not_accepted_as_empty_graph(self):
        llm = Mock()
        async def failure(**kwargs): return "cloud providers failed"
        llm.generate_answer = failure
        extractor = EntityExtractor(llm)
        with self.assertRaises(ValueError):
            asyncio.run(extractor.extract_graph("A document."))

    def test_llm_router_always_has_local_model_and_consistent_default(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True), patch("alana_system.inference.llm_engine.Router") as router:
            from alana_system.inference.llm_engine import LLMEngine
            engine = LLMEngine()
        self.assertTrue(engine.sovereign_mode)
        self.assertEqual(len(router.call_args.kwargs["model_list"]), 1)
        self.assertEqual(router.call_args.kwargs["model_list"][0]["litellm_params"]["model"], engine.local_model)

    def test_crawler_rejects_private_and_non_root_domains(self):
        from unittest.mock import patch
        from alana_system.qa_system.crawler import WebCrawler
        crawler = WebCrawler()
        self.assertFalse(crawler._is_public_url("http://127.0.0.1/admin"))
        self.assertFalse(crawler._is_public_url("http://[::1]/admin"))
        with patch("alana_system.qa_system.crawler.socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.4", 80))]):
            self.assertFalse(crawler._is_public_url("https://attacker.example/"))
        with patch("alana_system.qa_system.crawler.socket.getaddrinfo", return_value=[(None, None, None, None, ("8.8.8.8", 443))]):
            self.assertTrue(crawler._is_public_url("https://public.example/"))
        self.assertFalse(crawler._is_valid("https://other.example/", set(), start_host="public.example"))

    def test_blackboard_writes_atomic_snapshot_and_validates_namespace(self):
        import json
        import threading
        from alana_system.agent.core.blackboard import MissionBlackboard
        with tempfile.TemporaryDirectory() as root:
            board = MissionBlackboard.__new__(MissionBlackboard)
            board.storage_path = Path(root) / "tenant.json"
            board._save_lock = threading.Lock()
            board._save_revision = 0
            board._save_sync({"confirmed_facts": ["persisted"]}, 0)
            self.assertEqual(json.loads(board.storage_path.read_text(encoding="utf-8"))["confirmed_facts"], ["persisted"])
        with self.assertRaises(ValueError):
            MissionBlackboard("../outside")

    def test_graph_bridge_uses_correct_edges_and_hops(self):
        graph = Mock()
        graph.get_all_edges.return_value = [("A", "links_to", "B")]
        intelligence = GraphIntelligence(graph, Mock(), Mock(), Mock(), entity_vector_store=Mock())
        intelligence.bridge.call = Mock(return_value=["B"])
        intelligence.get_neighborhood("A", hops=2, namespace="tenant")
        payload = intelligence.bridge.call.call_args.args[0]
        self.assertEqual(payload["edges"], [{"from": "A", "to": "B", "type": "links_to"}])
        self.assertEqual(payload["hops"], 2)

    def test_graph_reconciliation_indexes_all_fact_endpoints(self):
        import numpy as np
        graph = Mock()
        graph.get_entity.return_value = None
        vectors = Mock()
        vectors.search.return_value = []
        embedder = Mock()
        embedder.embed_query.return_value = np.array([1.0, 0.0])
        intelligence = GraphIntelligence(graph, Mock(), Mock(), embedder, entity_vector_store=vectors)
        schema = KnowledgeGraphSchema(entities=[], relations=[{"subject": "A", "predicate": "connects", "object": "B"}])
        asyncio.run(intelligence.reconcile_graph(schema, "tenant-a"))
        self.assertEqual(vectors.upsert_entities.call_count, 2)

    def test_sensory_buffers_and_alerts_are_namespace_scoped(self):
        sensory = SensoryManager()
        device_a, device_b = Mock(), Mock()
        device_a.send_json = AsyncMock()
        device_b.send_json = AsyncMock()
        sensory.register_stream(device_a, "tenant-a")
        sensory.register_stream(device_b, "tenant-b")
        sensory.vision_buffer["tenant-a"].append({"content": "A"})
        self.assertEqual(sensory.get_last_vision("tenant-a")["content"], "A")
        self.assertIsNone(sensory.get_last_vision("tenant-b"))
        async def send(): await sensory.broadcast_alert("private", "tenant-a")
        asyncio.run(send())
        device_a.send_json.assert_awaited_once()
        device_b.send_json.assert_not_awaited()

    def test_iot_voice_rejects_invalid_namespace_before_processing(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from alana_system.iot.router import iot_router

        app = FastAPI()
        app.include_router(iot_router)
        with TestClient(app) as client:
            response = client.post(
                "/iot/voice",
                data={"namespace": "../outside"},
                files={"audio": ("sample.wav", b"audio", "audio/wav")},
            )
        self.assertEqual(response.status_code, 422)


from qdrant_client.http.models import FieldCondition, Filter, MatchValue


if __name__ == "__main__":
    unittest.main()
