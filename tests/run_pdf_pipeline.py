"""
PDF pipeline smoke test — FULL FLOW
Runs pages 14-16 of a PDF through:
  1. PDFProcessor  (text extraction + chunking)
  2. LLMExtractor  (structured concept extraction)
  3. LLM-as-judge  (evaluation of extraction quality)
  4. GraphIngestor (write concepts to Neo4j)
  5. Neo4j readback (verify ingestion succeeded)

Usage (from project root, with .venv activated):
    python tests/run_pdf_pipeline.py
"""

import asyncio
import os
import sys

# Ensure project root is on sys.path so absolute imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env from services/ directory
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", ".env")
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

from langfuse import Langfuse

from services.pipeline.processors.pdf_processor import PDFProcessor
from services.pipeline.processors.llm_extractor import LLMExtractor
from services.pipeline.processors.graph_ingestor import GraphIngestor
from tests.evaluation.evaluate_extraction import evaluate_extraction

# PDF_PATH = r"c:\Users\User\OneDrive\שולחן העבודה\Stav\Agents\agency-ontology\docs\idf-alias-and-names.pdf"
PDF_PATH = r"C:\Users\User\OneDrive\שולחן העבודה\Stav\Agents\agency-ontology\docs\בחינה במודלים חישוביים 2024 קיץ  מועד ב.pdf"
MODEL = "gpt-4o"
PAGES = (13, 16)  # 0-indexed; extracts pages 14-16

# ── Neo4j config (falls back to .env / environment) ──────────────────────────
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "changeme")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL")


async def run_pipeline_on_pdf(pdf_path: str) -> None:
    print(f"Starting pipeline on: {pdf_path}")

    # ── 1. Extract text ────────────────────────────────────────────────────────
    print("\n1. Extracting text via PDFProcessor...")
    pdf_processor = PDFProcessor()
    raw_text = ""

    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        for i in range(PAGES[0], min(PAGES[1], len(pdf.pages))):
            page_text = pdf.pages[i].extract_text()
            if page_text:
                raw_text += pdf_processor._normalize_hebrew(page_text) + "\n"

    print(f"   Extracted {len(raw_text)} chars of normalized text.")

    # ── 2. LLM Extraction ──────────────────────────────────────────────────────
    print("\n2. Running LLM Extractor...")
    api_key = os.environ["OPENAI_API_KEY"]
    langfuse_client = Langfuse()
    trace_id = "test-run-pdf-001"
    langfuse_client.trace(id=trace_id, name="pdf-pipeline-smoke-test")

    extractor = LLMExtractor(
        api_key=api_key or "ollama",
        model=MODEL,
        langfuse_client=langfuse_client,
        max_retries=1,
        base_url=OLLAMA_BASE_URL,
    )

    extraction_output = await extractor.extract(
        chunk_content=raw_text,
        document_title="IDF Alias & Names",
        section_title="Pages 14-16",
        page_range="14-16",
        job_id="smoke-test-job-001",
        trace_id=trace_id,
        primary_language="he",
    )

    print(f"   Extracted {len(extraction_output.concepts)} concepts.")
    for concept in extraction_output.concepts:
        print(
            f"     - {concept.name_he or concept.name} ({concept.concept_type}): "
            f"{(concept.description_he or concept.description)[:80]}..."
        )

    # ── 3. LLM-as-a-judge Evaluation ──────────────────────────────────────────
    print("\n3. Running LLM-as-a-judge evaluation...")
    concepts_json = extraction_output.model_dump_json(indent=2, exclude_unset=True)

    eval_result = await evaluate_extraction(
        source_text=raw_text,
        extracted_concepts=concepts_json,
        extraction_trace_id=trace_id,
    )

    print(f"   Factual accuracy: {eval_result.factual_accuracy}/5")
    print(f"   Hebrew compliance: {eval_result.hebrew_language_compliance}/5")
    print(f"   Reasoning: {eval_result.justification[:200]}...")
    print(f"   Suggested improvement: {eval_result.improvement}")

    # ── 4. Graph Ingestion ─────────────────────────────────────────────────────
    print("\n4. Ingesting to Neo4j graph...")
    try:
        ingestor = await GraphIngestor.create(
            uri=NEO4J_URI,
            user=NEO4J_USER,
            password=NEO4J_PASSWORD,
        )

        stats = await ingestor.ingest(
            extraction=extraction_output,
            document_id="smoke-test-doc-idf-alias",
            source_title="IDF Alias & Names",
            chunk_id="pages-14-16",
            connector_id="smoke-test",
        )

        print(f"   Ingested: {stats['concepts']} concepts, "
              f"{stats['relationships']} relationships, "
              f"{stats['data_mappings']} data mappings "
              f"({stats['errors']} errors)")

        # ── 5. Neo4j Readback Verification ────────────────────────────────────
        print("\n5. Verifying Neo4j ingestion (readback check)...")
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (c:Concept)
                WHERE $source IN c.sources
                RETURN c.name AS name, c.nameHe AS nameHe,
                       c.conceptType AS type, c.confidence AS conf
                ORDER BY c.confidence DESC
                LIMIT 10
                """,
                source="IDF Alias & Names",
            )
            found = []
            async for record in result:
                found.append(record)

        await driver.close()
        await ingestor.close()

        if found:
            print(f"   ✓ {len(found)} concepts found in Neo4j:")
            for r in found:
                name = r["nameHe"] or r["name"]
                print(f"     - {name} [{r['type']}] (conf={r['conf']:.2f})")
        else:
            print("   ⚠ No concepts found in Neo4j — check Neo4j connection / credentials.")

    except Exception as exc:
        print(f"   ✗ Graph ingestion failed: {exc}")
        print("     (Is Neo4j running? Check NEO4J_URI / NEO4J_PASSWORD in services/.env)")

    langfuse_client.flush()
    print("\n========= PIPELINE SMOKE TEST COMPLETE =========")


if __name__ == "__main__":
    asyncio.run(run_pipeline_on_pdf(PDF_PATH))
