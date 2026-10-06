import logging
import os
import time
import concurrent.futures
import asyncio
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from .text_extractor import TextExtractor, PageText
from .cleaner import TextCleaner
from .audio_transcriber import AudioTranscriber
from .note_loader import NoteLoader
from .note_extractor import NoteExtractor
from ..preprocessing.chunker import TextChunker
from ..memory.graph_store import GraphStore
from ..memory.vector_store import VectorStore
from ..memory.intelligence import GraphIntelligence
from ..embeddings.embedder import TextEmbedder
from ..preprocessing.entity_extractor import EntityExtractor
from ..core.resources import gatekeeper

logger = logging.getLogger("alana.ingestion.manager")
SUPPORTED_FILE_EXTENSIONS = frozenset({".pdf", ".txt", ".md", ".docx", ".mp3", ".wav", ".m4a"})

class IngestionManager:
    """
    Orquestrador Omni de Ingestao (Versao Industrial).
    - Suporta: PDF, Audio, Notas, DOCX, TXT.
    - Checkpoints: Resiliencia via SQL (retoma de onde parou).
    - Idempotencia: Baseada em Hash de Conteudo.
    - Isolamento: Suporte total a Namespaces.
    """

    def __init__(
        self, 
        graph_store: GraphStore, 
        vector_store: VectorStore, 
        intelligence: GraphIntelligence,
        max_workers: int = 2,
        extractor: Optional[TextExtractor] = None,
        cleaner: Optional[TextCleaner] = None,
        chunker: Optional[TextChunker] = None,
        embedder: Optional[TextEmbedder] = None
    ):
        self.extractor = extractor or TextExtractor()
        self.cleaner = cleaner or TextCleaner()
        self.chunker = chunker or TextChunker()
        self.embedder = embedder or TextEmbedder()
        self.audio_transcriber = None  # Lazy loading
        self.note_extractor = NoteExtractor()
        
        self.graph_store = graph_store
        self.vector_store = vector_store
        self.intelligence = intelligence
        self.entity_extractor = EntityExtractor(llm=self.intelligence.llm_engine)
        self.max_workers = max_workers
        self.llm_semaphore = asyncio.Semaphore(self.max_workers)
        
        # Parâmetros industriais de chunking ajustáveis
        self.llm_batch_size = 3000
        self.llm_batch_overlap = 500

    async def process_directory(self, directory_path: str, namespace: str = "global", mode: str = "fast"):
        """Processa todos os arquivos de um diretorio com inteligencia e checkpoints."""
        path = Path(directory_path)
        if not path.exists():
            logger.error(f"Pasta nao encontrada: {directory_path}")
            return

        files = [f for f in path.glob("**/*.*") if f.is_file() and not f.name.startswith(".")]
        logger.info(f"📂 Iniciando Ingestao Omni: {len(files)} arquivos no namespace '{namespace}'")

        # Processamento sequencial de arquivos para gerenciar VRAM (Ollama/Whisper)
        failures = []
        for file_path in files:
            try:
                await self.process_file(str(file_path), namespace, mode)
            except Exception as e:
                logger.error(f"Falha ao processar {file_path.name}: {e}")
                failures.append(f"{file_path.name}: {e}")
        if failures:
            raise RuntimeError(f"Falha ao processar {len(failures)} de {len(files)} arquivos: " + "; ".join(failures))

    async def process_file(self, file_path: str, namespace: str = "global", mode: str = "fast"):
        """Fluxo industrial assíncrono: Hash -> Checkpoint -> Extracao -> IA -> Vetores."""
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FILE_EXTENSIONS:
            raise ValueError(f"Formato não suportado: {suffix or '(sem extensão)'}. Suportados: {', '.join(sorted(SUPPORTED_FILE_EXTENSIONS))}.")
        content_hash = self.extractor.get_file_hash(path)
        filename = path.name

        # Adaptive Batching: Protege a GPU no modo exaustivo
        if mode == "deep":
            self.llm_batch_size = 1500
        else:
            self.llm_batch_size = 3000

        model_id = getattr(self.intelligence.llm_engine, "default_model", None) or getattr(self.intelligence.llm_engine, "local_model", "unknown")
        if not isinstance(model_id, str):
            model_id = "unknown"
        chunker_max = getattr(self.chunker, "max_chars", None)
        chunker_overlap = getattr(self.chunker, "overlap_chars", None)
        chunker_max = chunker_max if isinstance(chunker_max, int) else None
        chunker_overlap = chunker_overlap if isinstance(chunker_overlap, int) else None
        checkpoint_fingerprint = hashlib.sha256(json.dumps([
            content_hash, "ingestion-v3-grounded-page", mode, self.llm_batch_size, self.llm_batch_overlap,
            model_id, chunker_max, chunker_overlap,
        ], ensure_ascii=False).encode("utf-8")).hexdigest()
        file_hash = checkpoint_fingerprint

        # Registra antes da extração para que PDFs sem camada de texto não desapareçam do histórico.
        self.graph_store.register_ingestion_job(file_hash, filename, 0, namespace)

        # 1. Verifica Checkpoint Geral
        processed_batches = self.graph_store.get_processed_batches(file_hash, namespace)
        
        # 2. Extracao de Texto (CPU bound, mas mantemos síncrono por simplicidade ou to_thread)
        try:
            if suffix in {".pdf", ".txt", ".md", ".docx"}:
                raw_pages = await asyncio.to_thread(self.extractor.extract_text, path)
            else:
                if not self.audio_transcriber:
                    self.audio_transcriber = AudioTranscriber()
                async with gatekeeper.get_semaphore():
                    raw_pages = await asyncio.to_thread(self.audio_transcriber.transcribe, path)
        except Exception as exc:
            self.graph_store.update_job_status(file_hash, namespace, "FAILED", str(exc))
            raise

        if not raw_pages or not any(page.text.strip() for page in raw_pages):
            message = "Nenhum texto extraível encontrado. Se este PDF for digitalizado, OCR ainda não está configurado."
            self.graph_store.update_job_status(file_hash, namespace, "FAILED", message)
            raise RuntimeError(message)

        try:
            first_text = next(page.text for page in raw_pages if page.text.strip())
            doc_domain = await self.intelligence.detect_document_type(first_text)
            cleaned_pages = self.cleaner.clean_pages(raw_pages)
            if not any(page.text.strip() for page in cleaned_pages):
                raise RuntimeError("A limpeza removeu todo o texto extraído; documento não indexado.")
            chunks = self.chunker.chunk_pages(cleaned_pages, source_name=filename)
            if not chunks:
                raise RuntimeError(f"Chunker não produziu trechos para {filename}; ingestão interrompida.")
        except Exception as exc:
            self.graph_store.update_job_status(file_hash, namespace, "FAILED", str(exc))
            raise

        # 4. Agrupamento Semantico para Extracao via IA (Contexto para Ollama)
        extraction_batches = self._prepare_extraction_batches(cleaned_pages, filename)
        total_batches = len(extraction_batches)
        
        # Registra o job no banco para rastreamento
        self.graph_store.register_ingestion_job(file_hash, filename, total_batches, namespace)

        # 5. Extracao de Grafo (Com Checkpoint por Lote)
        logger.info(f"🧠 Extraindo Conhecimento [{namespace}]: {filename} ({total_batches} lotes)")
        
        # Usamos um Semaphore local para proteger a memória da GPU durante extrações massivas (Ponto 2 Auditoria)
        async def _bounded_batch_process(text, p_num, b_num):
            async with self.llm_semaphore:
                return await self._process_knowledge_batch(text, file_hash, filename, p_num, b_num, namespace, mode, doc_domain)

        tasks = []
        for text, p_num, b_num in extraction_batches:
            if b_num in processed_batches:
                continue # Pula o que ja foi feito
            tasks.append(_bounded_batch_process(text, p_num, b_num))

        if tasks:
            await asyncio.gather(*tasks)

        # 6. Indexacao Vetorial (Usa to_thread para o SentenceTransformer CPU/GPU bound)
        logger.info(f"🔢 Gerando Embeddings: {filename}")
        try:
            embedded_chunks = await asyncio.to_thread(self.embedder.embed_chunks, chunks)
            if chunks and len(embedded_chunks) != len(chunks):
                raise RuntimeError(f"Embeddings incompletos: {len(embedded_chunks)}/{len(chunks)}.")
            self.vector_store.upsert_embeddings(embedded_chunks, namespace=namespace)
        except Exception as exc:
            self.graph_store.update_job_status(file_hash, namespace, "FAILED", str(exc))
            raise

        # 7. Finaliza Job com sucesso
        self.graph_store.update_job_status(file_hash, namespace, "COMPLETED")
        logger.info(f"✅ Arquivo finalizado com sucesso: {filename}")

    def _prepare_extraction_batches(self, pages: List[Any], filename: str) -> List[tuple]:
        """Divide páginas longas sem misturar páginas, preservando proveniência exata."""
        batches = []
        max_size = max(1, self.llm_batch_size)
        overlap_size = min(max(0, self.llm_batch_overlap), max_size - 1)

        for p in pages:
            text = p.text or ""
            start = 0
            while start < len(text):
                end = min(start + max_size, len(text))
                batches.append((text[start:end], p.page_number, len(batches) + 1))
                if end == len(text):
                    break
                start = end - overlap_size
            
        return batches

    async def _process_knowledge_batch(self, text, file_hash, filename, page_num, batch_num, namespace, mode, domain="Tecnologia"):
        """Processa um lote individual de conhecimento de forma assíncrona."""
        try:
            # Extrai Grafo via LLM dinamicamente conforme o modo e o domínio
            graph_data = await self.entity_extractor.extract_graph(text, mode=mode, domain=domain)
            
            if graph_data.entities or graph_data.relations:
                # RECONCILIAÇÃO SEMÂNTICA (Ponto 3 Auditoria)
                # Unifica entidades similares para evitar fragmentação do grafo
                for entity in graph_data.entities:
                    entity.name = await self.intelligence.reconcile_entity(entity.name, namespace)
                
                for rel in graph_data.relations:
                    rel.subject = await self.intelligence.reconcile_entity(rel.subject, namespace)
                    rel.object = await self.intelligence.reconcile_entity(rel.object, namespace)

                self.graph_store.add_knowledge(
                    graph=graph_data,
                    source_doc=filename,
                    page_number=page_num,
                    namespace=namespace
                )
            
            # Marca batch como concluido no SQL
            self.graph_store.mark_batch_complete(file_hash, namespace, batch_num)
        except Exception as e:
            logger.error(f"Erro no lote {batch_num} de {filename}: {e}")
            self.graph_store.update_job_status(file_hash, namespace, "FAILED", str(e))
            raise
