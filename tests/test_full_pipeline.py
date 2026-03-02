"""
E2E integration test for the full Agency Ontology pipeline.

Tests the complete flow:
  PDF → PDFProcessor → LLMExtractor → EntityResolver → GraphIngestor → Neo4j

Run with:
    pytest tests/test_full_pipeline.py -v -s -m integration

Requirements:
  - OPENAI_API_KEY must be set in the environment or services/.env
  - Neo4j must be running and accessible (NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD)
  - The IDF PDF must exist at the path below (or set PDF_PATH env var)
"""
from __future__ import annotations

import logging
import os
import sys
import uuid

import pytest
import pytest_asyncio

# ── Logging setup — rich output even without -s ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_full_pipeline")

# Ensure project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", ".env")
    if os.path.exists(_env):
        load_dotenv(_env)
        logger.info(f"Loaded .env from {_env}")
    else:
        logger.warning(f".env not found at {_env} — relying on shell variables")
except ImportError:
    logger.warning("python-dotenv not installed, relying on shell variables")

# ── Configuration ──────────────────────────────────────────────────────────────

PDF_PATH = os.environ.get(
    "PDF_PATH",
    # r"c:\Users\User\OneDrive\שולחן העבודה\Stav\Agents\agency-ontology\docs\idf-alias-and-names.pdf",
    r"C:\Users\User\OneDrive\שולחן העבודה\Stav\Agents\agency-ontology\docs\בחינה במודלים חישוביים 2024 קיץ  מועד ב.pdf",
)
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "changeme")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("PIPELINE_MODEL", "gpt-4o")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL")

# Unique source tag per test run so cleanup is surgical
TEST_SOURCE_TAG = f"pytest-run-{uuid.uuid4().hex[:8]}"
# DOCUMENT_TITLE = f"IDF Alias Test [{TEST_SOURCE_TAG}]"
DOCUMENT_TITLE = f"Test file smaller [{TEST_SOURCE_TAG}]"

logger.info(f"Test run tag: {TEST_SOURCE_TAG}")
logger.info(f"PDF path: {PDF_PATH}")
logger.info(f"Neo4j URI: {NEO4J_URI}")
logger.info(f"Model: {MODEL}")
logger.info(f"OPENAI_API_KEY set: {'YES' if OPENAI_API_KEY else 'NO'}")

# ── Marks ──────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.integration


# ── Pre-collection checks (fail fast w/ a clear message) ──────────────────────

def _check_prereqs():
    """Verify preconditions before any fixture is set up."""
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY is not set (add it to services/.env or shell)")
    if not os.path.exists(PDF_PATH):
        missing.append(f"PDF not found: {PDF_PATH!r}  (set PDF_PATH env var to override)")
    if missing:
        pytest.skip("Prerequisites not met:\n  " + "\n  ".join(missing))


# ── Helper — create a fresh Neo4j driver in the CURRENT event loop ─────────────

async def neo4j_connect():
    """
    Create a fresh Neo4j AsyncDriver bound to the current event loop.
    Caller is responsible for closing it.
    Skips if Neo4j is unreachable.
    """
    from neo4j import AsyncGraphDatabase
    try:
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        await driver.verify_connectivity()
        return driver
    except Exception as exc:
        pytest.skip(f"Neo4j not available at {NEO4J_URI}: {exc}")


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def orchestrator():
    """
    PipelineOrchestrator shared across all tests in this session.
    Creates its own Neo4j driver internally — works fine across loops
    because the ingestor creates sessions lazily per-call.
    """
    _check_prereqs()

    # Verify Neo4j is reachable before wasting time on the LLM
    driver = await neo4j_connect()
    await driver.close()

    logger.info(f"Creating PipelineOrchestrator (model={MODEL}) ...")
    from services.pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator(
        neo4j_uri=NEO4J_URI,
        neo4j_user=NEO4J_USER,
        neo4j_password=NEO4J_PASSWORD,
        openai_api_key=OPENAI_API_KEY,
        model=MODEL,
        max_concurrent_chunks=2,
        ollama_base_url=OLLAMA_BASE_URL,
    )
    yield orch
    logger.info("Closing orchestrator ...")
    await orch.close()


@pytest_asyncio.fixture(scope="session")
async def pipeline_result(orchestrator):
    """Run the full pipeline once; all tests assert on the shared result."""
    logger.info(f"Running pipeline on: {PDF_PATH}")
    logger.info(f"Document title: {DOCUMENT_TITLE}")

    result = await orchestrator.run_pdf(
        pdf_path=PDF_PATH,
        document_title=DOCUMENT_TITLE,
        connector_id=TEST_SOURCE_TAG,
        job_id=TEST_SOURCE_TAG,
    )

    logger.info(f"Pipeline finished: {result}")
    logger.info(f"  chunks_processed : {result.chunks_processed}")
    logger.info(f"  concepts_ingested: {result.concepts_ingested}")
    logger.info(f"  relationships    : {result.relationships_ingested}")
    logger.info(f"  data_mappings    : {result.data_mappings_ingested}")
    logger.info(f"  errors           : {result.errors}")
    logger.info(f"  duration_seconds : {result.duration_seconds:.1f}s")

    yield result

    # ── Teardown: clean up test concepts after session ──────────────────────
    logger.info(f"[Teardown] Cleaning up concepts with source={DOCUMENT_TITLE!r} ...")
    try:
        driver = await neo4j_connect()
        async with driver.session() as sess:
            res = await sess.run(
                "MATCH (c:Concept) WHERE $tag IN c.sources "
                "DETACH DELETE c RETURN count(c) AS deleted",
                tag=DOCUMENT_TITLE,
            )
            rec = await res.single()
            deleted = rec["deleted"] if rec else 0
            logger.info(f"[Teardown] Deleted {deleted} test concept(s)")
        await driver.close()
    except Exception as exc:
        logger.warning(f"[Teardown] Cleanup failed (non-fatal): {exc}")


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_completes(pipeline_result):
    """Pipeline must complete without being marked as skipped."""
    logger.info(f"[test] pipeline_completes: skipped={pipeline_result.skipped}, errors={pipeline_result.errors}")
    assert not pipeline_result.skipped, (
        f"Pipeline was skipped. Errors: {pipeline_result.errors}"
    )


@pytest.mark.asyncio
async def test_pipeline_processes_chunks(pipeline_result):
    """Pipeline must process at least one text chunk."""
    logger.info(f"[test] chunks_processed={pipeline_result.chunks_processed}")
    assert pipeline_result.chunks_processed >= 1, (
        f"Expected ≥1 chunk, got {pipeline_result.chunks_processed}. "
        "Check PDF text extraction — is pdfplumber installed? Is OCR needed?"
    )


@pytest.mark.asyncio
async def test_pipeline_extracts_concepts(pipeline_result):
    """LLM must extract at least one concept."""
    logger.info(f"[test] concepts_ingested={pipeline_result.concepts_ingested}")
    assert pipeline_result.concepts_ingested >= 1, (
        f"Expected ≥1 concept, got {pipeline_result.concepts_ingested}. "
        "Errors: {pipeline_result.errors}"
    )


@pytest.mark.asyncio
async def test_concepts_in_neo4j(pipeline_result):
    """Concepts must be physically present in Neo4j."""
    logger.info(f"[test] Querying Neo4j for source={DOCUMENT_TITLE!r} ...")
    driver = await neo4j_connect()
    try:
        async with driver.session() as session:
            result = await session.run(
                "MATCH (c:Concept) WHERE $src IN c.sources RETURN count(c) AS cnt",
                src=DOCUMENT_TITLE,
            )
            record = await result.single()
            count = record["cnt"] if record else 0
    finally:
        await driver.close()

    logger.info(f"[test] Neo4j concepts found: {count}")
    assert count >= 1, (
        f"Expected ≥1 concept in Neo4j, found {count}. "
        "Possible causes: Neo4j MERGE failed (check agent-langfuse-worker logs), "
        "or credentials mismatch."
    )


@pytest.mark.asyncio
async def test_concepts_have_required_fields(pipeline_result):
    """Every ingested concept must have name, conceptType, status=CANDIDATE, valid confidence."""
    driver = await neo4j_connect()
    try:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (c:Concept)
                WHERE $src IN c.sources
                RETURN c.name AS name, c.conceptType AS type,
                       c.status AS status, c.confidence AS conf
                LIMIT 50
                """,
                src=DOCUMENT_TITLE,
            )
            concepts = [r async for r in result]
    finally:
        await driver.close()

    logger.info(f"[test] Checking {len(concepts)} concept(s) for required fields")
    assert len(concepts) >= 1, "No concepts returned from Neo4j for field validation"

    for c in concepts:
        assert c["name"], f"Concept missing 'name': {dict(c)}"
        assert c["type"], f"Concept '{c['name']}' missing 'conceptType'"
        assert c["status"] == "CANDIDATE", (
            f"Expected status=CANDIDATE, got {c['status']!r} for '{c['name']}'"
        )
        conf = c["conf"]
        assert conf is not None and 0.0 <= float(conf) <= 1.0, (
            f"Invalid confidence {conf!r} for '{c['name']}'"
        )


@pytest.mark.asyncio
async def test_terms_linked_to_concepts(pipeline_result):
    """Every concept must have at least one HAS_TERM relationship."""
    driver = await neo4j_connect()
    try:
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (c:Concept) WHERE $src IN c.sources
                OPTIONAL MATCH (c)-[:HAS_TERM]->(t:Term)
                RETURN c.name AS concept, count(t) AS term_count
                LIMIT 50
                """,
                src=DOCUMENT_TITLE,
            )
            rows = [r async for r in result]
    finally:
        await driver.close()

    orphaned = [r["concept"] for r in rows if r["term_count"] == 0]
    logger.info(f"[test] Orphaned concepts (no terms): {orphaned}")
    assert not orphaned, (
        f"Concepts without any Term: {orphaned}. "
        "Check GraphIngestor._ingest_concept term merge logic."
    )


@pytest.mark.asyncio
async def test_pipeline_has_no_fatal_errors(pipeline_result):
    """Error count must not exceed chunk count (allow occasional transient failures)."""
    error_count = len(pipeline_result.errors)
    chunk_count = pipeline_result.chunks_processed
    logger.info(f"[test] errors={error_count}, chunks={chunk_count}")
    assert error_count <= max(chunk_count, 1), (
        f"Too many errors ({error_count}) for {chunk_count} chunks: "
        f"{pipeline_result.errors}"
    )


# ── Hierarchical extraction tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_hierarchy_stats_tracked(pipeline_result):
    """
    PipelineRunResult must track hierarchy-related stats.
    Values will be 0 for flat docs — but the attributes must exist.
    """
    assert hasattr(pipeline_result, "labels_ingested"), "labels_ingested missing from PipelineRunResult"
    assert hasattr(pipeline_result, "statements_ingested"), "statements_ingested missing"
    assert hasattr(pipeline_result, "hierarchy_edges_ingested"), "hierarchy_edges_ingested missing"
    logger.info(
        f"[test] hierarchy stats — labels={pipeline_result.labels_ingested} "
        f"stmts={pipeline_result.statements_ingested} edges={pipeline_result.hierarchy_edges_ingested}"
    )


@pytest.mark.asyncio
async def test_hierarchy_pipeline_with_dictionary_doctype():
    """
    Run the pipeline with document_type='PDF_DICTIONARY' on the same PDF.
    Forces the hierarchical extraction chain.
    Skipped if there is no OPENAI_API_KEY.
    """
    _check_prereqs()

    from services.pipeline.orchestrator import PipelineOrchestrator

    hier_tag = f"pytest-hier-{uuid.uuid4().hex[:6]}"
    hier_title = f"IDF Alias Hierarchical [{hier_tag}]"

    logger.info(f"[test] Running HIERARCHICAL pipeline run (tag={hier_tag}) ...")
    orch = PipelineOrchestrator(
        neo4j_uri=NEO4J_URI,
        neo4j_user=NEO4J_USER,
        neo4j_password=NEO4J_PASSWORD,
        openai_api_key=OPENAI_API_KEY,
        model=MODEL,
        max_concurrent_chunks=1,
        ollama_base_url=OLLAMA_BASE_URL,
    )
    try:
        result = await orch.run_pdf(
            pdf_path=PDF_PATH,
            document_title=hier_title,
            connector_id=hier_tag,
            job_id=hier_tag,
            document_type="PDF_DICTIONARY",
        )
    finally:
        await orch.close()

    logger.info(f"[test] Hierarchical result: {result}")
    assert not result.skipped, f"Pipeline skipped: {result.errors}"
    assert result.concepts_ingested >= 1, "No concepts ingested in hierarchical mode"

    # Check Neo4j for hierarchy edges using fresh driver
    driver = await neo4j_connect()
    try:
        async with driver.session() as session:
            res = await session.run("""
                MATCH (c:Concept)-[r:INSTANCE_OF|SUBCLASS_OF|PART_OF_HIERARCHY]->()
                WHERE $tag IN c.sources
                RETURN count(r) AS edge_count
            """, tag=hier_title)
            rec = await res.single()
            edge_count = rec["edge_count"] if rec else 0

        logger.info(f"[test] Hierarchy edges in Neo4j: {edge_count}")
        logger.info(f"[test] Result hierarchy stats: labels={result.labels_ingested} stmts={result.statements_ingested} edges={result.hierarchy_edges_ingested}")

        if edge_count == 0:
            logger.warning(
                "[test] No hierarchy edges found — document may not have strong hierarchy signals."
            )

        # Cleanup
        async with driver.session() as session:
            await session.run(
                "MATCH (c:Concept) WHERE $tag IN c.sources DETACH DELETE c",
                tag=hier_title,
            )
        logger.info(f"[test] Hierarchical test concepts cleaned up")
    finally:
        await driver.close()


@pytest.mark.asyncio
async def test_neo4j_hierarchy_schema_exists():
    """Verify that neo4j has the required hierarchy constraints and indexes."""
    driver = await neo4j_connect()
    try:
        async with driver.session() as session:
            result = await session.run(
                "SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names"
            )
            rec = await result.single()
            constraint_names = rec["names"] if rec else []
    finally:
        await driver.close()

    logger.info(f"[test] Neo4j constraints: {constraint_names}")
    assert "label_unique" in constraint_names, (
        "label_unique constraint missing — run init.cypher on neo4j"
    )
    assert "statement_unique" in constraint_names, (
        "statement_unique constraint missing — run init.cypher on neo4j"
    )
