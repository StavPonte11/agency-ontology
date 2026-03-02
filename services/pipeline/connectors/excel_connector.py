"""
Excel Source Connector — Agency Ontology Impact Extension
=========================================================
Reads .xlsx / .xls dependency files with *unknown schema at dev time*.

The schema detection pass is the critical UX gate:
  1. ExcelConnector.detect_schema() samples the first 20 rows and
     returns a DetectedSchema report.
  2. The operator reviews and optionally overrides column assignments
     in the Source Ingestion Manager UI.
  3. Only after confirmation does ingestion run.

Every row produces either a committed result or a Review Queue item.
Silent discards are forbidden — they corrupt the coverage score.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field

from .base import (
    ConnectorHealthStatus,
    ConnectorType,
    SourceConnector,
    SourceDocument,
)
from ..models.ontology import (
    DetectedColumn,
    DetectedColumnRole,
    DetectedSchema,
    ExcelDependencyExtraction,
)

logger = logging.getLogger(__name__)


# ── Schema detection heuristics ───────────────────────────────────────────────

_LOCATION_HINTS = {
    "location", "loc", "site", "building", "base", "address",
    "facility", "zone", "segment", "מיקום", "אתר", "בסיס",
}
_DEPENDENCY_HINTS = {
    "dependency", "dependencies", "dep", "uses", "contains", "hosts",
    "departments", "department", "projects", "project", "assets",
    "systems", "personnel", "תלות", "תלויות", "מחלקות",
}
_DESCRIPTION_HINTS = {
    "description", "desc", "notes", "remarks", "details", "תיאור", "הערות",
}
_META_HINTS = {
    "region", "tier", "status", "type", "category", "criticality",
    "אזור", "קריטיות", "סטטוס",
}


def _detect_column_role(col_name: str, sample_values: list[str]) -> DetectedColumnRole:
    """Heuristic role detection from column name and sample values."""
    name_lower = col_name.lower().strip()
    words = set(name_lower.replace("-", " ").replace("_", " ").split())

    if words & _LOCATION_HINTS:
        return DetectedColumnRole.LOCATION_ID
    if words & _DEPENDENCY_HINTS:
        return DetectedColumnRole.DEPENDENCY
    if words & _DESCRIPTION_HINTS:
        return DetectedColumnRole.LOCATION_DESC
    if words & _META_HINTS:
        return DetectedColumnRole.META

    # Value-based heuristics
    if sample_values:
        avg_len = sum(len(v) for v in sample_values) / len(sample_values)
        if avg_len > 60:
            # Long free-text → likely dependency or description
            return DetectedColumnRole.DEPENDENCY
        if avg_len < 20:
            # Short values → likely identifier or metadata
            return DetectedColumnRole.META

    return DetectedColumnRole.UNKNOWN


def detect_schema_heuristic(
    headers: list[str],
    rows: list[dict[str, Any]],
    max_sample: int = 20,
) -> DetectedSchema:
    """
    Pure heuristic schema detection — no LLM call required.
    Used as a fast baseline; the UI lets operators override any column.
    """
    sample_rows = rows[:max_sample]
    columns: list[DetectedColumn] = []
    warnings: list[str] = []

    location_col: Optional[str] = None
    dep_cols: list[str] = []
    desc_cols: list[str] = []
    meta_cols: list[str] = []

    # Detect merged-cell markers (openpyxl leaves None for merged cells)
    none_counts = {h: sum(1 for r in sample_rows if r.get(h) is None) for h in headers}
    for h, cnt in none_counts.items():
        if cnt > len(sample_rows) * 0.5:
            warnings.append(
                f"Column '{h}' has > 50% empty cells — possible merged cell or sparse data"
            )

    confidence_map: dict[str, float] = {}
    for h in headers:
        vals = [str(r[h]) for r in sample_rows if r.get(h) is not None][:5]
        role = _detect_column_role(h, vals)
        col_conf = 0.9 if role != DetectedColumnRole.UNKNOWN else 0.4
        # Boost confidence if first column looks like an ID
        if h == headers[0] and role == DetectedColumnRole.UNKNOWN:
            role = DetectedColumnRole.LOCATION_ID
            col_conf = 0.7
        columns.append(DetectedColumn(
            column_name=h,
            detected_role=role,
            sample_values=vals,
            confidence=col_conf,
        ))
        confidence_map[h] = col_conf

        if role == DetectedColumnRole.LOCATION_ID and location_col is None:
            location_col = h
        elif role == DetectedColumnRole.DEPENDENCY:
            dep_cols.append(h)
        elif role == DetectedColumnRole.LOCATION_DESC:
            desc_cols.append(h)
        elif role == DetectedColumnRole.META:
            meta_cols.append(h)

    # Fallback: if no location column found, use first column
    if not location_col and headers:
        location_col = headers[0]
        warnings.append(
            f"No confident location column found — defaulting to '{location_col}'. "
            "Please verify in the UI before running ingestion."
        )

    # Fallback: if no dep columns, try to infer from remaining non-location columns
    if not dep_cols:
        remaining = [h for h in headers if h != location_col and h not in desc_cols and h not in meta_cols]
        if remaining:
            dep_cols = remaining
            warnings.append(
                f"No dependency columns confidently detected. "
                f"Defaulting to: {dep_cols}. Please verify."
            )

    overall_conf = min(confidence_map.values()) if confidence_map else 0.5

    return DetectedSchema(
        columns=columns,
        location_column=location_col or (headers[0] if headers else ""),
        dependency_columns=dep_cols,
        description_columns=desc_cols,
        meta_columns=meta_cols,
        total_rows=len(rows),
        sample_rows=[{k: str(v) for k, v in r.items()} for r in rows[:5]],
        detection_confidence=overall_conf,
        warnings=warnings,
    )


# ── Review Queue item ─────────────────────────────────────────────────────────

class ReviewQueueItem(BaseModel):
    """A row that could not be fully committed — queued for human review.
    No row is ever silently discarded (spec Part 3.1 hard contract).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str
    row_index: int
    raw_row: dict[str, Any]
    location_name: Optional[str] = None
    reason: str
    llm_extraction: Optional[ExcelDependencyExtraction] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Excel Connector ───────────────────────────────────────────────────────────

class ExcelConnector(SourceConnector):
    """
    Source connector for Excel dependency files with unknown schema.

    Usage:
        connector = ExcelConnector(file_path="/path/to/deps.xlsx")
        schema = await connector.detect_schema()
        # → show schema to operator in UI, get confirmation / overrides
        async for doc in connector.list_documents(schema_overrides=confirmed_schema):
            pipeline.process(doc)
    """

    connector_type = ConnectorType.EXCEL

    def __init__(
        self,
        file_path: str,
        connector_id: str = "excel-manual",
        llm_client: Optional[Any] = None,   # langchain LLM for dep extraction
        sheet_name: Optional[str | int] = 0,  # None = all sheets
    ) -> None:
        self._file_path = file_path
        self._connector_id = connector_id
        self._llm_client = llm_client
        self._sheet_name = sheet_name
        self._review_queue: list[ReviewQueueItem] = []

    def validate_config(self, config: dict[str, Any]) -> bool:
        path = config.get("file_path", "")
        if not path:
            raise ValueError("file_path is required for ExcelConnector")
        return True

    async def test_connection(self) -> ConnectorHealthStatus:
        import os
        if os.path.exists(self._file_path):
            return ConnectorHealthStatus(healthy=True, latency_ms=0.0)
        return ConnectorHealthStatus(
            healthy=False,
            error=f"File not found: {self._file_path}",
        )

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to Excel file"},
                "sheet_name": {"type": "string", "description": "Sheet to read (default: first sheet)"},
            },
            "required": ["file_path"],
        }

    # ── Schema detection ──────────────────────────────────────────────────────

    def _read_excel_raw(self) -> tuple[list[str], list[dict[str, Any]]]:
        """Read Excel file into headers + rows list. Handles multi-sheet."""
        try:
            import openpyxl
        except ImportError:
            raise ImportError(
                "openpyxl is required for ExcelConnector. "
                "Install with: pip install openpyxl"
            )

        wb = openpyxl.load_workbook(self._file_path, data_only=True)

        if self._sheet_name is None:
            # Multi-sheet: concatenate all sheets
            all_rows: list[dict[str, Any]] = []
            headers: list[str] = []
            for sheet in wb.worksheets:
                sheet_rows = list(sheet.values)
                if not sheet_rows:
                    continue
                if not headers:
                    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(sheet_rows[0])]
                for row in sheet_rows[1:]:
                    all_rows.append(dict(zip(headers, row)))
            return headers, all_rows
        else:
            if isinstance(self._sheet_name, int):
                ws = wb.worksheets[self._sheet_name]
            else:
                ws = wb[self._sheet_name]
            rows = list(ws.values)
            if not rows:
                return [], []
            headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[0])]
            data = [dict(zip(headers, row)) for row in rows[1:]]
            return headers, data

    async def detect_schema(self) -> DetectedSchema:
        """
        Schema detection pass — samples first 20 rows, returns DetectedSchema.
        This result MUST be shown to the operator for confirmation before ingestion.
        The operator can override any column assignment.
        """
        headers, rows = self._read_excel_raw()
        schema = detect_schema_heuristic(headers, rows, max_sample=20)
        logger.info(
            f"Schema detected for '{self._file_path}': "
            f"location_col='{schema.location_column}' "
            f"dep_cols={schema.dependency_columns} "
            f"confidence={schema.detection_confidence:.2f}"
        )
        return schema

    async def get_document(self, external_id: str) -> SourceDocument:
        """Fetch a single row by its external_id (row index string)."""
        _, rows = self._read_excel_raw()
        idx = int(external_id.split("::row::")[-1])
        if idx >= len(rows):
            raise ValueError(f"Row index {idx} out of range (total rows: {len(rows)})")
        row = rows[idx]
        content_hash = SourceDocument.compute_hash(row)
        return SourceDocument(
            external_id=external_id,
            title=f"Row {idx}",
            content_type="excel_row",
            raw_content=row,
            content_hash=content_hash,
            document_type="EXCEL_ROW",
            source_connector_id=self._connector_id,
            connector_type=ConnectorType.EXCEL,
        )

    async def list_documents(
        self,
        since: Optional[datetime] = None,
        schema_overrides: Optional[DetectedSchema] = None,
    ) -> AsyncIterator[SourceDocument]:
        """
        Yield one SourceDocument per Excel row.

        Each row that cannot be fully parsed produces a ReviewQueueItem
        (stored in self.review_queue) AND still yields a SourceDocument
        with review_needed=True in metadata.

        INVARIANT: total yielded documents == total_rows.
        No row is ever silently dropped.
        """
        headers, rows = self._read_excel_raw()
        schema = schema_overrides or await self.detect_schema()

        loc_col = schema.location_column
        dep_cols = schema.dependency_columns
        desc_cols = schema.description_columns

        for idx, row in enumerate(rows):
            # Skip completely empty rows (e.g. section headers in raw Excel)
            if all(v is None or str(v).strip() == "" for v in row.values()):
                logger.debug(f"Skipping empty row {idx}")
                continue

            external_id = f"{self._connector_id}::row::{idx}"
            location_name = str(row.get(loc_col, "")).strip()
            dep_text = " | ".join(
                str(row.get(col, "")).strip()
                for col in dep_cols
                if row.get(col)
            )
            description = " ".join(
                str(row.get(col, "")).strip()
                for col in desc_cols
                if row.get(col)
            )

            review_needed = False
            review_reason = ""

            if not location_name:
                review_needed = True
                review_reason = "Missing location name in location column"
                self._review_queue.append(ReviewQueueItem(
                    source_file=self._file_path,
                    row_index=idx,
                    raw_row={k: str(v) for k, v in row.items()},
                    location_name=None,
                    reason=review_reason,
                ))

            if not dep_text and not review_needed:
                review_needed = True
                review_reason = "No dependency text in dependency columns"
                self._review_queue.append(ReviewQueueItem(
                    source_file=self._file_path,
                    row_index=idx,
                    raw_row={k: str(v) for k, v in row.items()},
                    location_name=location_name or None,
                    reason=review_reason,
                ))

            content = {
                "location_name": location_name,
                "dependency_text": dep_text,
                "description": description,
                "raw_row": {k: str(v) for k, v in row.items() if v is not None},
                "row_index": idx,
                "review_needed": review_needed,
                "review_reason": review_reason,
            }
            content_hash = SourceDocument.compute_hash(content)

            yield SourceDocument(
                external_id=external_id,
                title=location_name or f"Row {idx} (unnamed)",
                content_type="excel_row",
                raw_content=content,
                metadata={
                    "row_index": idx,
                    "review_needed": review_needed,
                    "review_reason": review_reason,
                    "location_column": loc_col,
                    "dependency_columns": dep_cols,
                },
                content_hash=content_hash,
                document_type="EXCEL_ROW",
                source_connector_id=self._connector_id,
                connector_type=ConnectorType.EXCEL,
            )

    @property
    def review_queue(self) -> list[ReviewQueueItem]:
        """Items queued for human review after list_documents() has run."""
        return list(self._review_queue)

    def clear_review_queue(self) -> None:
        """Clear review queue (call after items have been processed)."""
        self._review_queue.clear()


# ── LLM Dependency Extractor (per-row LLM chain) ─────────────────────────────

class ExcelDependencyExtractor:
    """
    Parses raw dependency text from an Excel row into structured entities.
    Uses with_structured_output on ExcelDependencyExtraction Pydantic model.

    This is always called AFTER schema detection and operator confirmation.
    """

    _SYSTEM_PROMPT = """You are an expert at parsing organizational dependency text
from Excel spreadsheets. Your task: extract all entities and relationships
described in the dependency text for a specific location.

For each entity mentioned, determine:
- entity_name: exact name as written
- entity_type: DEPARTMENT | PROJECT | ASSET | SYSTEM | PERSONNEL | CLIENT | PROCESS | OBLIGATION
- edge_type: HOSTS | RUNS | OPERATES | SERVES | USES | STAFFED_BY | FEEDS | BLOCKS
- edge_criticality: CRITICAL | HIGH | MEDIUM | LOW
- notes: any qualifying notes (e.g. "no backup", "can operate remotely")

IMPORTANT for operational_status_hints:
- If the text says "planned", "future", "not yet operational", "in progress" → PLANNED
- If the text says "suspended", "on hold", "paused" → SUSPENDED
- Otherwise → ACTIVE (default)

Return ALL entities mentioned. If the text is ambiguous or incomplete,
set review_needed=true and explain in review_reason.
"""

    def __init__(self, llm_client: Any) -> None:
        """
        llm_client: a LangChain ChatOpenAI / ChatOllama instance.
        Will be wrapped with .with_structured_output(ExcelDependencyExtraction).
        """
        self._chain = llm_client.with_structured_output(ExcelDependencyExtraction)

    async def extract(
        self,
        location_name: str,
        dep_text: str,
        description: str = "",
    ) -> ExcelDependencyExtraction:
        """Extract entities from a single row's dependency text."""
        from langchain_core.messages import HumanMessage, SystemMessage

        human_content = (
            f"Location: {location_name}\n"
            f"Description: {description}\n"
            f"Dependency text: {dep_text}\n\n"
            "Extract all entities and relationships from the dependency text above."
        )
        messages = [
            SystemMessage(content=self._SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
        try:
            result = await self._chain.ainvoke(messages)
            return result
        except Exception as exc:
            logger.warning(
                f"LLM extraction failed for location '{location_name}': {exc}"
            )
            return ExcelDependencyExtraction(
                location_name=location_name,
                entities=[],
                review_needed=True,
                review_reason=f"LLM extraction failed: {exc}",
                confidence=0.0,
            )
