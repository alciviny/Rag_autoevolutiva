import logging
import os
import time
import concurrent.futures
import asyncio
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
        for file_path in files:
            try:
                await self.process_file(str(file_path), namespace, mode)
            except Exception as e:
                logger.error(f"Falha ao processar {file_path.name}: {e}")

    async def process_file(self, file_path: str, namespace: str = "global", mode: str = "fast"):
        """Fluxo industrial assíncrono: Hash -> Checkpoint -> Extracao -> IA -> Vetores."""
        path = Path(file_path)
        file_hash = self.extractor.get_file_hash(path)
        filename = path.name
        suffix = path.suffix.lower()

        # Adaptive Batching: Protege a GPU no modo exaustivo
        if mode == "deep":
            self.llm_batch_size = 1500
        else:
            self.llm_batch_size = 3000

        # 1. Verifica Checkpoint Geral
        processed_batches = self.graph_store.get_processed_batches(file_hash, namespace)
        
        # 2. Extracao de Texto (CPU bound, mas mantemos síncrono por simplicidade ou to_thread)
        if suffix == ".pdf" or suffix in [".txt", ".md", ".docx"]:
            # Extracao pode ser pesada, usamos to_thread para nao travar o loop principal
            raw_pages = await asyncio.to_thread(self.extractor.extract_text, path)
        elif suffix in [".mp3", ".wav", ".m4a"]:
            if not self.audio_transcriber:
                self.audio_transcriber = AudioTranscriber()
            
            # Whisper é pesado, usamos o ResourceGatekeeper para proteger a VRAM
            async with gatekeeper.get_semaphore():
                raw_pages = await asyncio.to_thread(self.audio_transcriber.transcribe, path)
        else:
            return # Formato ignorado

        if not raw_pages:
            return

        # Auto-Descoberta de Domínio
        doc_domain = "Tecnologia e Negócios"
        if raw_pages and raw_pages[0].text:
            doc_domain = await self.intelligence.detect_document_type(raw_pages[0].text)

        # 3. Limpeza e Chunking (RAG)
        cleaned_pages = self.cleaner.clean_pages(raw_pages)
        chunks = self.chunker.chunk_pages(cleaned_pages, source_name=filename)

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
        embedded_chunks = await asyncio.to_thread(self.embedder.embed_chunks, chunks)
        self.vector_store.upsert_embeddings(embedded_chunks, namespace=namespace)

        # 7. Finaliza Job com sucesso
        self.graph_store.update_job_status(file_hash, namespace, "COMPLETED")
        logger.info(f"✅ Arquivo finalizado com sucesso: {filename}")

    def _prepare_extraction_batches(self, pages: List[Any], filename: str) -> List[tuple]:
        """Agrupa paginas para otimizar chamadas ao Ollama."""
        batches = []
        current_text = ""
        current_page = 1
        
        for p in pages:
            if len(current_text) + len(p.text) < self.llm_batch_size:
                current_text += "\n" + p.text
            else:
                if current_text:
                    batches.append((current_text, current_page, len(batches) + 1))
                
                context_overlap = current_text[-self.llm_batch_overlap:] if len(current_text) > self.llm_batch_overlap else current_text
                current_text = context_overlap + "\n" + p.text
                current_page = p.page_number
        
        if current_text:
            batches.append((current_text, current_page, len(batches) + 1))
            
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
