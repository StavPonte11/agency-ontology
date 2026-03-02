"""
Excel Connector Tests — Agency Ontology Impact Extension
=========================================================
Tests the ExcelConnector's schema detection, per-row yield invariant,
idempotency, and review queue behavior.

A critical invariant: total yielded docs == total_rows (minus empty rows).
No row is ever silently discarded.

Run with:
    pytest tests/backend/test_excel_connector.py -v -s -m impact
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

pytestmark = pytest.mark.impact


# ── Helpers to create test Excel files in memory ──────────────────────────────

def _make_excel_bytes(rows: list[dict], sheet_name: str = "Sheet1") -> bytes:
    """Create a minimal Excel file in memory. Returns bytes."""
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl is not installed — cannot run Excel connector tests")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name

    if not rows:
        return b""

    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_excel_tempfile(rows: list[dict], suffix: str = ".xlsx") -> str:
    """Write Excel rows to a temp file. Returns file path."""
    content = _make_excel_bytes(rows)
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


# ── Test data definitions ─────────────────────────────────────────────────────

_STANDARD_ROWS = [
    {"Location": "Location Alpha", "Dependencies": "Department A, Department B", "Notes": "Primary"},
    {"Location": "Location Beta",  "Dependencies": "Department C, System X",     "Notes": "Secondary"},
    {"Location": "Location Gamma", "Dependencies": "Project Z (PLANNED)",        "Notes": ""},
]

_PARTIAL_ROWS = [
    {"Location": "Location X",  "Dependencies": "Department A",  "Notes": "OK"},
    {"Location": "",            "Dependencies": "Department B",  "Notes": "Missing location"},
    {"Location": "Location Y",  "Dependencies": "",              "Notes": "Missing deps"},
    {"Location": "",            "Dependencies": "",              "Notes": "Fully empty"},
]

_ALTERNATE_SCHEMA_ROWS = [
    {"site": "Site 1", "contains": "Dept Alpha; Dept Beta", "region": "North"},
    {"site": "Site 2", "contains": "Project X (PLANNED)", "region": "South"},
]


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schema_detection_standard_layout():
    """Schema detection must correctly identify location and dependency columns."""
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_STANDARD_ROWS)
    try:
        connector = ExcelConnector(file_path=path)
        schema = await connector.detect_schema()

        assert schema.location_column, "location_column must be non-empty"
        assert schema.dependency_columns, "dependency_columns must be non-empty"
        assert schema.total_rows == len(_STANDARD_ROWS), (
            f"Expected {len(_STANDARD_ROWS)} rows, got {schema.total_rows}"
        )
        assert len(schema.sample_rows) > 0, "sample_rows must be populated"

        # 'Location' should be detected as the location column
        assert schema.location_column.lower() in ("location", "site"), (
            f"Expected 'Location' as location column, got {schema.location_column!r}"
        )
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_schema_detection_alternate_headers():
    """Schema detection must handle non-standard column names (site, contains, region)."""
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_ALTERNATE_SCHEMA_ROWS)
    try:
        connector = ExcelConnector(file_path=path)
        schema = await connector.detect_schema()

        assert schema.location_column, "location_column required even with alternate headers"
        assert len(schema.columns) == 3, f"Expected 3 columns, got {len(schema.columns)}"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_no_silent_discards_on_partial_rows():
    """
    Core invariant: every non-empty row produces either a committed SourceDocument
    or a ReviewQueueItem. No row is ever silently discarded.

    _PARTIAL_ROWS has 4 rows. The fully-empty row (Location='', Deps='')
    is skipped (blank), so we expect at minimum 3 documents + 2 review items.
    """
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_PARTIAL_ROWS)
    try:
        connector = ExcelConnector(file_path=path)
        schema = await connector.detect_schema()

        docs = []
        async for doc in connector.list_documents(schema_overrides=schema):
            docs.append(doc)

        # At least 3 docs from 4 rows (fully empty row may be skipped)
        assert len(docs) >= 3, (
            f"Expected ≥ 3 documents from 4 rows. Got {len(docs)}. "
            "Rows with missing location or dependencies must still produce docs."
        )

        # Items that had missing location or deps must have review_needed=True
        review_docs = [d for d in docs if d.metadata.get("review_needed")]
        assert len(review_docs) >= 2, (
            f"Expected ≥ 2 docs with review_needed=True (missing location, missing deps). "
            f"Got {len(review_docs)}"
        )

        # Review queue must contain entries
        rq = connector.review_queue
        assert len(rq) >= 2, (
            f"Expected ≥ 2 ReviewQueueItems. Got {len(rq)}. "
            "Missing location name and missing dep text must both enqueue review items."
        )
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_review_queue_has_reasoning():
    """ReviewQueueItems must have a non-empty reason string."""
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_PARTIAL_ROWS)
    try:
        connector = ExcelConnector(file_path=path)
        schema = await connector.detect_schema()
        async for _ in connector.list_documents(schema_overrides=schema):
            pass

        for item in connector.review_queue:
            assert item.reason, f"ReviewQueueItem missing reason: {item}"
            assert item.source_file == path
            assert item.row_index >= 0
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_idempotency():
    """
    Idempotency test: running list_documents twice on the same file
    must produce the same content_hash values in the same order.
    """
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_STANDARD_ROWS)
    try:
        connector1 = ExcelConnector(file_path=path)
        schema = await connector1.detect_schema()

        hashes_run1 = []
        async for doc in connector1.list_documents(schema_overrides=schema):
            hashes_run1.append(doc.content_hash)

        connector2 = ExcelConnector(file_path=path)
        hashes_run2 = []
        async for doc in connector2.list_documents(schema_overrides=schema):
            hashes_run2.append(doc.content_hash)

        assert hashes_run1 == hashes_run2, (
            f"Idempotency failed: hashes differ between run 1 ({hashes_run1}) "
            f"and run 2 ({hashes_run2})"
        )
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_document_external_ids_are_unique():
    """Every yielded document must have a unique external_id."""
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_STANDARD_ROWS)
    try:
        connector = ExcelConnector(file_path=path)
        schema = await connector.detect_schema()

        ids = []
        async for doc in connector.list_documents(schema_overrides=schema):
            ids.append(doc.external_id)

        assert len(ids) == len(set(ids)), (
            f"Duplicate external_ids found: {[x for x in ids if ids.count(x) > 1]}"
        )
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_schema_detection_produces_sample_rows():
    """DetectedSchema must include up to 5 sample rows for UI preview."""
    from services.pipeline.connectors.excel_connector import ExcelConnector

    path = _write_excel_tempfile(_STANDARD_ROWS)
    try:
        connector = ExcelConnector(file_path=path)
        schema = await connector.detect_schema()

        assert len(schema.sample_rows) >= 1, "sample_rows must have at least 1 row for preview"
        assert len(schema.sample_rows) <= 5, "sample_rows should have at most 5 rows"

        first = schema.sample_rows[0]
        assert isinstance(first, dict), "sample_rows entries must be dicts"
    finally:
        os.unlink(path)


def test_detect_column_role_location_hints():
    """Column name 'Location' must map to LOCATION_ID role."""
    from services.pipeline.connectors.excel_connector import _detect_column_role
    from services.pipeline.models.ontology import DetectedColumnRole

    role = _detect_column_role("Location", [])
    assert role == DetectedColumnRole.LOCATION_ID


def test_detect_column_role_dependency_hints():
    """Column name 'Dependencies' must map to DEPENDENCY role."""
    from services.pipeline.connectors.excel_connector import _detect_column_role
    from services.pipeline.models.ontology import DetectedColumnRole

    role = _detect_column_role("Dependencies", [])
    assert role == DetectedColumnRole.DEPENDENCY


def test_detect_column_role_long_values_is_dependency():
    """Column with long free-text values should default to DEPENDENCY."""
    from services.pipeline.connectors.excel_connector import _detect_column_role
    from services.pipeline.models.ontology import DetectedColumnRole

    long_vals = ["Department A runs Project X and also manages System Y with critical backup"] * 3
    role = _detect_column_role("col_1", long_vals)
    assert role in (DetectedColumnRole.DEPENDENCY, DetectedColumnRole.LOCATION_DESC), (
        f"Long text values should map to DEPENDENCY or LOCATION_DESC, got {role}"
    )
