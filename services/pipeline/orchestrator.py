"""
Pipeline Orchestrator — Agency Ontology
Runs the full ingestion pipeline end-to-end:
  PDFConnector → PDFProcessor → LLMExtractor → EntityResolver → GraphIngestor

Usage:
    import asyncio
    from services.pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="changeme",
        openai_api_key="sk-...",
        model="gpt-4o",
    )
    result = asyncio.run(orchestrator.run_pdf("/path/to/doc.pdf"))
    print(result)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    """Summary of a single document pipeline run."""

    document_id: str
    document_title: str
    chunks_processed: int = 0
    concepts_ingested: int = 0
    relationships_ingested: int = 0
    data_mappings_ingested: int = 0
    labels_ingested: int = 0
    statements_ingested: int = 0
    hierarchy_edges_ingested: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    skipped: bool = False

    def __str__(self) -> str:
        status = "SKIPPED" if self.skipped else "OK" if not self.errors else "PARTIAL"
        hier = f" labels={self.labels_ingested} stmts={self.statements_ingested} edges={self.hierarchy_edges_ingested}" \
               if (self.labels_ingested or self.hierarchy_edges_ingested) else ""
        return (
            f"[{status}] {self.document_title!r} | "
            f"chunks={self.chunks_processed} concepts={self.concepts_ingested} "
            f"rels={self.relationships_ingested} mappings={self.data_mappings_ingested}"
            f"{hier} errors={len(self.errors)} ({self.duration_seconds:.1f}s)"
        )


class PipelineOrchestrator:
    """
    Full pipeline: PDF → text chunks → LLM extraction → entity resolution → Neo4j.

    One instance is meant to be reused across multiple documents (shared driver/extractor).
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        openai_api_key: str = "",
        model: str = "gpt-4o",
        langfuse_client: Optional[Any] = None,
        max_concurrent_chunks: int = 3,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        max_retries: int = 1,
        elasticsearch_url: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ) -> None:
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._openai_api_key = openai_api_key
        self._model = model
        self._langfuse = langfuse_client
        self._max_concurrent = max_concurrent_chunks
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_retries = max_retries
        self._elasticsearch_url = elasticsearch_url
        self._ollama_base_url = ollama_base_url

        # Lazily initialized
        self._ingestor: Optional[Any] = None
        self._extractor: Optional[Any] = None
        self._es: Optional[Any] = None

    async def _get_ingestor(self):
        """Lazily create and cache the GraphIngestor (also ensures indexes)."""
        if self._ingestor is None:
            from .processors.graph_ingestor import GraphIngestor
            self._ingestor = await GraphIngestor.create(
                uri=self._neo4j_uri,
                user=self._neo4j_user,
                password=self._neo4j_password,
            )
        return self._ingestor

    async def _get_es(self):
        """Lazily initialise the Elasticsearch service if URL is configured."""
        if self._es is None and self._elasticsearch_url:
            from elasticsearch import AsyncElasticsearch
            self._es = AsyncElasticsearch([self._elasticsearch_url], request_timeout=30)
        return self._es

    def _get_extractor(self):
        """Lazily create and cache the LLMExtractor (uses ChatOpenAI)."""
        if self._extractor is None:
            from .processors.llm_extractor import LLMExtractor
            self._extractor = LLMExtractor(
                api_key=self._openai_api_key or "ollama",
                model=self._model,
                langfuse_client=self._langfuse,
                max_retries=self._max_retries,
                base_url=self._ollama_base_url,  # None → OpenAI; set → Ollama-compatible endpoint
            )
        return self._extractor

    async def close(self) -> None:
        """Close underlying Neo4j driver and Elasticsearch client."""
        if self._ingestor is not None:
            await self._ingestor.close()
        if self._es is not None:
            await self._es.close()

    async def run_pdf(
        self,
        pdf_path: str,
        document_title: Optional[str] = None,
        connector_id: str = "manual",
        job_id: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> PipelineRunResult:
        """
        Run the full pipeline on a single PDF file.

        Args:
            pdf_path:       Absolute path to the PDF file.
            document_title: Override display title (defaults to filename stem).
            connector_id:   Connector identifier for provenance (e.g. 'pdf-manual').
            job_id:         Correlation job ID for LangFuse tracing.
            document_type:  Optional document classification hint for the LLM extractor.
                            Values: 'PDF_DICTIONARY' | 'CATALOG' | 'REPORT' | etc.
                            When 'PDF_DICTIONARY' or 'CATALOG', enables hierarchical extraction.

        Returns:
            PipelineRunResult with counts and errors.
        """
        start = time.monotonic()
        path = Path(pdf_path)

        if not path.exists():
            return PipelineRunResult(
                document_id="unknown",
                document_title=str(pdf_path),
                errors=[f"File not found: {pdf_path}"],
                skipped=True,
            )

        title = document_title or path.stem
        document_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(path.resolve())))
        job_id = job_id or str(uuid.uuid4())

        logger.info(f"Pipeline start: {title!r} (doc_id={document_id}, job_id={job_id})")

        result = PipelineRunResult(
            document_id=document_id,
            document_title=title,
        )

        # ── Step 1: Extract text + split into chunks ──────────────────────────
        logger.info(f"--- [Step 1/3] Extracting text and chunking ---")
        try:
            from .processors.pdf_processor import PDFProcessor

            processor = PDFProcessor(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
            pdf_bytes = path.read_bytes()
            chunks = processor.process(
                pdf_bytes=pdf_bytes,
                document_id=document_id,
                document_title=title,
            )
            logger.info(f"PDF split into {len(chunks)} chunks.")
        except Exception as exc:
            logger.exception(f"PDF processing failed for {title!r}: {exc}")
            result.errors.append(f"PDF processing: {exc}")
            result.duration_seconds = time.monotonic() - start
            return result

        if not chunks:
            logger.warning(f"No text extracted from {title!r} — skipping.")
            result.skipped = True
            result.duration_seconds = time.monotonic() - start
            return result

        # ── Step 2: LLM extract + ingest each chunk (with concurrency limit) ──
        logger.info(f"--- [Step 2/3] Extracting concepts from {len(chunks)} chunks (concurrency={self._max_concurrent}) ---")
        from .resolution.entity_resolver import EntityResolver

        resolver = EntityResolver()
        extractor = self._get_extractor()
        ingestor = await self._get_ingestor()

        semaphore = asyncio.Semaphore(self._max_concurrent)

        # Track progress across concurrent tasks
        total_chunks = len(chunks)
        completed = 0
        running_concepts = 0
        running_rels = 0

        async def process_chunk(chunk, chunk_idx: int):
            nonlocal completed, running_concepts, running_rels
            async with semaphore:
                trace_id = f"{job_id}::{chunk.chunk_id}"
                chunk_start = time.monotonic()
                logger.info(
                    f"[{chunk_idx + 1}/{total_chunks}] ▶ Extracting chunk {chunk.chunk_id} "
                    f"({len(chunk.content)} chars) ..."
                )
                try:
                    extraction = await extractor.extract(
                        chunk_content=chunk.content,
                        document_title=title,
                        section_title=chunk.section_title or "",
                        page_range=chunk.page_range,
                        job_id=job_id,
                        trace_id=trace_id,
                        primary_language="he" if chunk.has_hebrew else "en",
                        document_type=document_type,  # drives hierarchical model selection
                    )
                except Exception as exc:
                    completed += 1
                    logger.error(
                        f"[{completed}/{total_chunks}] ❌ Chunk {chunk.chunk_id} FAILED "
                        f"({time.monotonic() - chunk_start:.1f}s): {exc}"
                    )
                    return {"concepts": 0, "relationships": 0, "data_mappings": 0, "errors": 1}

                # Deduplication: skip concepts the resolver already knows
                new_concepts = []
                for concept in extraction.concepts:
                    existing_id = resolver.resolve(concept.name)
                    if existing_id is None:
                        new_concepts.append(concept)
                        # Register ALL term forms for future dedup
                        concept_id_placeholder = f"{document_id}::{concept.name}"
                        resolver.register(concept.name, concept_id_placeholder)
                        if hasattr(concept, "name_he") and concept.name_he:
                            resolver.register(concept.name_he, concept_id_placeholder)

                # Always ingest (ingestor uses MERGE — duplicates are safe)
                stats = await ingestor.ingest(
                    extraction=extraction,
                    document_id=document_id,
                    source_title=title,
                    chunk_id=chunk.chunk_id,
                    connector_id=connector_id,
                )

                chunk_elapsed = time.monotonic() - chunk_start
                completed += 1
                running_concepts += stats.get("concepts", 0)
                running_rels += stats.get("relationships", 0)
                logger.info(
                    f"[{completed}/{total_chunks}] ✅ Chunk {chunk.chunk_id} done in {chunk_elapsed:.1f}s — "
                    f"+{stats.get('concepts', 0)} concepts, +{stats.get('relationships', 0)} rels "
                    f"(running totals: {running_concepts} concepts, {running_rels} rels)"
                )
                return stats

        chunk_tasks = [process_chunk(chunk, i) for i, chunk in enumerate(chunks)]
        all_stats = await asyncio.gather(*chunk_tasks)

        for stats in all_stats:
            result.chunks_processed += 1
            result.concepts_ingested       += stats.get("concepts", 0)
            result.relationships_ingested  += stats.get("relationships", 0)
            result.data_mappings_ingested  += stats.get("data_mappings", 0)
            result.labels_ingested         += stats.get("labels", 0)
            result.statements_ingested     += stats.get("statements", 0)
            result.hierarchy_edges_ingested += stats.get("hierarchy_edges", 0)
            if stats.get("errors", 0):
                result.errors.append(f"chunk error count: {stats['errors']}")

        logger.info(f"--- [Step 3/3] Finalizing results ---")
        result.duration_seconds = time.monotonic() - start
        logger.info(
            f"\n" + "="*60 + "\n"
            f"  Pipeline COMPLETE: {title!r}\n"
            f"  Chunks processed : {result.chunks_processed}/{total_chunks}\n"
            f"  Concepts ingested: {result.concepts_ingested}\n"
            f"  Relationships    : {result.relationships_ingested}\n"
            f"  Duration         : {result.duration_seconds:.1f}s\n"
            + "="*60
        )
        return result

    async def run_directory(
        self,
        directory: str,
        glob_pattern: str = "**/*.pdf",
        connector_id: str = "pdf-directory",
        job_id: Optional[str] = None,
    ) -> list[PipelineRunResult]:
        """
        Run the pipeline on all PDFs in a directory (recursive by default).

        Args:
            directory:    Absolute path to directory containing PDFs.
            glob_pattern: Glob for PDF discovery (default: all PDFs recursively).
            connector_id: Source connector ID for provenance.
            job_id:       Shared job ID for all documents in this run.

        Returns:
            List of PipelineRunResult, one per PDF found.
        """
        root = Path(directory)
        if not root.exists():
            logger.error(f"Directory not found: {directory}")
            return []

        job_id = job_id or str(uuid.uuid4())
        pdf_paths = sorted(root.glob(glob_pattern))

        if not pdf_paths:
            logger.warning(f"No PDFs found in {directory!r} with pattern {glob_pattern!r}")
            return []

        logger.info(f"Processing {len(pdf_paths)} PDFs from {directory!r} (job_id={job_id})")

        results = []
        for pdf_path in pdf_paths:
            result = await self.run_pdf(
                pdf_path=str(pdf_path),
                connector_id=connector_id,
                job_id=job_id,
            )
            results.append(result)
            logger.info(f"  {result}")

        total_concepts = sum(r.concepts_ingested for r in results)
        total_rels = sum(r.relationships_ingested for r in results)
        logger.info(
            f"Directory run complete: {len(results)} docs, "
            f"{total_concepts} concepts, {total_rels} relationships ingested."
        )
        return results

    async def run_excel(
        self,
        file_path: str,
        sheet_name: Optional[str | int] = 0,
        connector_id: str = "excel-impact",
        llm_extraction: bool = True,
        schema_overrides: Optional[Any] = None,
    ) -> Any:  # ExcelIngestionResult
        """
        Run the full impact ingestion pipeline on a single Excel file.

        Reads the file using ExcelConnector with column-aware schema detection,
        then for each row:
          1. Ingests Site / Facility / Component nodes and structured edges
             directly into Neo4j (no LLM needed for these).
          2. Optionally calls FacilityRowImpactExtractor on free-text columns
             to extract additional typed edges.
        """
        from .models.ontology import ExcelIngestionResult
        from .connectors.excel_connector import ExcelConnector, FacilityRowImpactExtractor

        start = time.monotonic()
        path = Path(file_path)

        if not path.exists():
            logger.error(f"Excel file not found: {file_path}")
            return ExcelIngestionResult(
                file_name=str(file_path),
                total_rows=0,
                committed_rows=0,
                review_queue_rows=0,
                new_entities=0,
                updated_entities=0,
                new_edges=0,
                entity_resolution_matched=0,
                entity_resolution_new=0,
                entity_resolution_ambiguous=0,
                errors=[f"File not found: {file_path}"],
            )

        connector = ExcelConnector(
            file_path=file_path,
            connector_id=connector_id,
            sheet_name=sheet_name,
        )

        # ── Step 1: Schema detection ──────────────────────────────────────────
        if schema_overrides:
            schema = schema_overrides
            logger.info(f"Using provided schema overrides for '{file_path}'")
        else:
            schema = await connector.detect_schema()
            logger.info(
                f"Schema detected: location_col='{schema.location_column}' "
                f"dep_cols={schema.dependency_columns} "
                f"confidence={schema.detection_confidence:.2f}"
            )
            if schema.warnings:
                for w in schema.warnings:
                    logger.warning(f"Schema warning: {w}")

        dataset_context = connector.analyze_dataset(schema)
        logger.info(f"Dataset global context extracted ({len(dataset_context)} chars).")

        # ── Step 2: Set up ChatOpenAI extractor (if LLM extraction requested) ─
        impact_extractor = None
        if llm_extraction:
            try:
                from langchain_openai import ChatOpenAI

                llm_kwargs: dict[str, Any] = {
                    "model": self._model,
                    "temperature": 0.0,
                    "api_key": self._openai_api_key or "ollama",
                }
                if self._ollama_base_url:
                    # Ollama exposes an OpenAI-compatible endpoint — just point base_url
                    llm_kwargs["base_url"] = self._ollama_base_url

                llm_client = ChatOpenAI(**llm_kwargs)
                impact_extractor = FacilityRowImpactExtractor(llm_client, dataset_context=dataset_context)
                backend = self._ollama_base_url or "OpenAI"
                logger.info(f"FacilityRowImpactExtractor → ChatOpenAI (backend={backend}, model={self._model})")
            except Exception as exc:
                logger.warning(
                    f"Could not initialize ChatOpenAI extractor: {exc}. "
                    "Proceeding with structured-only ingestion (no free-text edges)."
                )

        # ── Step 3: Ingest each row ───────────────────────────────────────────
        ingestor = await self._get_ingestor()

        total_rows = 0
        committed_rows = 0
        review_queue_rows = 0
        total_nodes = 0
        total_edges = 0
        errors: list[str] = []

        async for doc in connector.list_documents(schema_overrides=schema):
            total_rows += 1
            raw = doc.raw_content

            if raw.get("review_needed"):
                review_queue_rows += 1
                logger.debug(
                    f"Row {raw.get('row_index')} queued for review: {raw.get('review_reason')}"
                )

            # ── LLM free-text extraction ──────────────────────────────────────
            llm_result = None
            if impact_extractor and raw.get("free_texts"):
                try:
                    llm_result = await impact_extractor.extract(
                        site_name=raw.get("site_name", ""),
                        facility_name=raw.get("facility_name", ""),
                        component_name=raw.get("component_name", ""),
                        free_texts=raw.get("free_texts", {}),
                    )
                    if llm_result.review_needed:
                        logger.debug(
                            f"LLM extraction flagged row {raw.get('row_index')} "
                            f"for review: {llm_result.review_reason}"
                        )
                except Exception as exc:
                    logger.warning(f"LLM extraction failed for row {raw.get('row_index')}: {exc}")

            # ── Graph ingestion (structured + LLM) ───────────────────────────
            try:
                row_stats = await ingestor.ingest_impact_row(
                    row_content=raw,
                    source_file=file_path,
                    llm_extraction=llm_result,
                )
                total_nodes += row_stats.get("nodes", 0)
                total_edges += row_stats.get("edges", 0)
                if row_stats.get("errors", 0):
                    errors.append(f"Row {raw.get('row_index')}: {row_stats['errors']} edge error(s)")
                else:
                    committed_rows += 1
            except Exception as exc:
                logger.error(f"Row {raw.get('row_index')} ingestion failed: {exc}")
                errors.append(f"Row {raw.get('row_index')}: ingestion failed: {exc}")

        duration = time.monotonic() - start
        logger.info(
            f"\n{'='*60}\n"
            f"  Excel Pipeline COMPLETE: {path.name!r}\n"
            f"  Total rows     : {total_rows}\n"
            f"  Committed rows : {committed_rows}\n"
            f"  Review queue   : {review_queue_rows}\n"
            f"  Nodes created  : {total_nodes}\n"
            f"  Edges created  : {total_edges}\n"
            f"  Review queue sz: {len(connector.review_queue)}\n"
            f"  Duration       : {duration:.1f}s\n"
            + '='*60
        )

        return ExcelIngestionResult(
            file_name=path.name,
            total_rows=total_rows,
            committed_rows=committed_rows,
            review_queue_rows=len(connector.review_queue),
            new_entities=total_nodes,
            updated_entities=0,
            new_edges=total_edges,
            entity_resolution_matched=0,
            entity_resolution_new=total_nodes,
            entity_resolution_ambiguous=review_queue_rows,
            errors=errors,
            duration_seconds=duration,
        )

    async def run_excel_directory(
        self,
        directory: str,
        glob_pattern: str = "**/*.xlsx",
        connector_id: str = "excel-impact",
        llm_extraction: bool = True,
    ) -> list[Any]:  # list[ExcelIngestionResult]
        """
        Run the Excel impact pipeline on all .xlsx files in a directory.
        """
        root = Path(directory)
        if not root.exists():
            logger.error(f"Directory not found: {directory}")
            return []

        excel_paths = sorted(root.glob(glob_pattern))
        if not excel_paths:
            logger.warning(f"No Excel files found in {directory!r} with pattern {glob_pattern!r}")
            return []

        logger.info(f"Processing {len(excel_paths)} Excel files from {directory!r}")

        results = []
        for excel_path in excel_paths:
            result = await self.run_excel(
                file_path=str(excel_path),
                connector_id=connector_id,
                llm_extraction=llm_extraction,
            )
            results.append(result)
            logger.info(
                f"  {excel_path.name}: {result.committed_rows}/{result.total_rows} rows committed, "
                f"{result.new_edges} edges"
            )

        total_edges = sum(r.new_edges for r in results)
        total_nodes = sum(r.new_entities for r in results)
        logger.info(
            f"Excel directory run complete: {len(results)} files, "
            f"{total_nodes} nodes, {total_edges} edges ingested."
        )
        return results
