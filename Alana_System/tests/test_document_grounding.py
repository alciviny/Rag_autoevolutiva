import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from alana_system.api.routes.ingestion import router as ingestion_router
from alana_system.memory.graph_store import GraphStore
from alana_system.preprocessing.entity_extractor import EntityExtractor, KnowledgeGraphSchema
from alana_system.query.query_engine import QueryEngine


class DocumentGroundingTests(unittest.TestCase):
    def test_extractor_discards_nonverbatim_evidence(self):
        source = "A célula fotovoltaica converte luz solar em eletricidade."
        llm = Mock()
        llm.generate_answer = AsyncMock(return_value=json.dumps({
            "entities": [
                {"name": "célula fotovoltaica", "type": "Componente", "description": "Converte luz em eletricidade.", "evidence": "A célula fotovoltaica"},
                {"name": "eletricidade", "type": "Conceito", "description": "Energia produzida.", "evidence": "A corrente é armazenada numa bateria."},
            ],
            "relations": [{
                "subject": "célula fotovoltaica", "predicate": "converte", "object": "eletricidade",
                "evidence": "converte luz solar em eletricidade",
            }],
        }, ensure_ascii=False))

        graph = asyncio.run(EntityExtractor(llm).extract_graph(source))
        self.assertEqual(graph.entities[0].evidence, "A célula fotovoltaica")
        self.assertEqual(graph.entities[1].evidence, "")
        self.assertEqual(graph.relations[0].evidence, "converte luz solar em eletricidade")

    def test_graph_persists_entity_and_relation_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph_store = GraphStore(str(Path(tmp) / "graph.sqlite"))
            graph = KnowledgeGraphSchema(
                entities=[
                    {"name": "Painel solar", "type": "Componente", "description": "", "evidence": "O painel solar produz energia."},
                    {"name": "Energia elétrica", "type": "Conceito", "description": "", "evidence": "produz energia elétrica"},
                ],
                relations=[{
                    "subject": "Painel solar", "predicate": "produz", "object": "Energia elétrica",
                    "evidence": "O painel solar produz energia elétrica.",
                }],
            )
            graph_store.add_knowledge(graph, "manual.pdf", 3, "global")

            with graph_store._connect() as conn:
                relation = conn.execute("SELECT source_doc, page_number, evidence FROM relations").fetchone()
                entity_sources = conn.execute("SELECT COUNT(*) FROM entity_evidence").fetchone()[0]
            self.assertEqual(tuple(relation), ("manual.pdf", 3, "O painel solar produz energia elétrica."))
            self.assertEqual(entity_sources, 2)
            facts = graph_store.query_subgraph(["Painel solar"], namespace="global")
            self.assertEqual(facts[0]["evidence"], "O painel solar produz energia elétrica.")

    def test_rag_context_shows_page_and_literal_evidence(self):
        engine = QueryEngine.__new__(QueryEngine)
        context = engine._build_hybrid_context([], [{
            "subject": "Painel solar", "relation": "produz", "object": "Energia elétrica",
            "source_doc": "manual.pdf", "page_number": 3,
            "evidence": "O painel solar produz energia elétrica.",
        }])
        self.assertIn("manual.pdf", context)
        self.assertIn("pág. 3", context)
        self.assertIn('evidência literal: "O painel solar produz energia elétrica."', context)

    def test_upload_keeps_original_name_and_rejects_unknown_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = FastAPI()
            app.include_router(ingestion_router)
            with patch("alana_system.api.routes.ingestion.namespace_workspace", side_effect=lambda _base, namespace: Path(tmp) / namespace), \
                 patch("alana_system.api.routes.ingestion._background_ingestion_task", new_callable=AsyncMock) as background:
                with TestClient(app) as client:
                    rejected = client.post(
                        "/ingestion/upload?namespace=local",
                        files={"file": ("archive.exe", b"data", "application/octet-stream")},
                    )
                    accepted = client.post(
                        "/ingestion/upload?namespace=local",
                        files={"file": ("manual final.pdf", b"pdf bytes", "application/pdf")},
                    )

            self.assertEqual(rejected.status_code, 415)
            self.assertEqual(accepted.status_code, 200)
            uploaded_path = background.await_args.args[0]
            self.assertEqual(uploaded_path.name, "manual final.pdf")
            self.assertEqual(uploaded_path.read_bytes(), b"pdf bytes")

    def test_telemetry_api_returns_sensor_readings_not_graph_hubs(self):
        from alana_system.api.dependencies import get_graph_store
        from alana_system.api.routes.admin import router as admin_router

        graph_store = Mock()
        graph_store.get_recent_telemetry.return_value = [{
            "entity_name": "Pump", "value": 20, "unit": "V", "raw_reading": "20 V", "timestamp": "now",
        }]
        app = FastAPI()
        app.include_router(admin_router, prefix="/api")
        app.dependency_overrides[get_graph_store] = lambda: graph_store
        with TestClient(app) as client:
            response = client.get("/api/telemetry/data?namespace=lab&limit=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["readings"][0]["raw_reading"], "20 V")
        graph_store.get_recent_telemetry.assert_called_once_with("lab", 10)
