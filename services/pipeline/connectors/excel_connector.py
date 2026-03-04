"""
Excel Source Connector — Agency Ontology Impact Extension
=========================================================
Reads .xlsx / .xls dependency files, including the known 36-column
facility/site/component schema — or any schema with unknown layout.

Two-phase approach:
  1. detect_schema() — heuristic column role detection (fast, no LLM).
     Output shown to operator for confirmation before ingestion.
  2. list_documents() — yields one SourceDocument per row.
     Each document carries all 36 typed columns in raw_content.
  3. FacilityRowImpactExtractor — LLM extraction from free-text columns.
     Produces typed edges (FacilityRowExtractionOutput).

The older ExcelDependencyExtractor is kept for backward-compatibility with
the generic (unknown schema) flow.

Every row produces either a committed result or a Review Queue item.
Silent discards are forbidden — they corrupt the coverage score.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
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
    FacilityRowExtractionOutput,
    ExtractedImpactEdge,
)

logger = logging.getLogger(__name__)


# ── Known column schema (36 columns) ─────────────────────────────────────────
# Maps exact (case-insensitive) column names → their roles.
# This lets schema detection skip heuristics when the file matches exactly.

_KNOWN_SCHEMA: dict[str, DetectedColumnRole] = {
    "id":                                        DetectedColumnRole.META,
    "site_name":                                 DetectedColumnRole.LOCATION_ID,
    "facility_name":                             DetectedColumnRole.FACILITY_ID,
    "component_name":                            DetectedColumnRole.COMPONENT_ID,
    "category":                                  DetectedColumnRole.CATEGORICAL,
    "responsible_body":                          DetectedColumnRole.STRUCTURED_REF,
    "system":                                    DetectedColumnRole.STRUCTURED_REF,
    "support_for_attack_effort":                 DetectedColumnRole.CATEGORICAL,
    "support_for_defende_control_effort":        DetectedColumnRole.CATEGORICAL,
    "support_for_defence_control_effort":        DetectedColumnRole.CATEGORICAL,
    "support_for_intelligence_effort":           DetectedColumnRole.CATEGORICAL,
    "support_for_allert_effort":                 DetectedColumnRole.CATEGORICAL,
    "support_for_alert_effort":                  DetectedColumnRole.CATEGORICAL,
    "support_for_national_effort":               DetectedColumnRole.CATEGORICAL,
    "ploygon":                                   DetectedColumnRole.GEO,
    "polygon":                                   DetectedColumnRole.GEO,
    "central_point":                             DetectedColumnRole.GEO,
    "details_on_facilty_purpose":                DetectedColumnRole.FREE_TEXT,
    "details_on_facility_purpose":               DetectedColumnRole.FREE_TEXT,
    "operational_significance_if_damaged":       DetectedColumnRole.FREE_TEXT,
    "sop_if_damaged":                            DetectedColumnRole.FREE_TEXT,
    "deffence_with_iron_dome":                   DetectedColumnRole.CATEGORICAL,
    "defence_with_iron_dome":                    DetectedColumnRole.CATEGORICAL,
    "level_for_deffense_with_upper_layer":       DetectedColumnRole.CATEGORICAL,
    "level_for_defence_with_upper_layer":        DetectedColumnRole.CATEGORICAL,
    "system_information":                        DetectedColumnRole.FREE_TEXT,
    "component_importance_to_system":            DetectedColumnRole.FREE_TEXT,
    "hardering":                                 DetectedColumnRole.META,
    "hardening":                                 DetectedColumnRole.META,
    "concelaments":                              DetectedColumnRole.META,
    "concealment":                               DetectedColumnRole.META,
    "sidtibution":                               DetectedColumnRole.META,
    "distribution":                              DetectedColumnRole.META,
    "distribution_details":                      DetectedColumnRole.FREE_TEXT,
    "recovery_capability":                       DetectedColumnRole.META,
    "redundency":                                DetectedColumnRole.META,
    "redundancy":                                DetectedColumnRole.META,
    "redundency_details":                        DetectedColumnRole.FREE_TEXT,
    "redundancy_details":                        DetectedColumnRole.FREE_TEXT,
    "primary_backup":                            DetectedColumnRole.STRUCTURED_REF,
    "secondary_primary":                         DetectedColumnRole.STRUCTURED_REF,
    "mobility":                                  DetectedColumnRole.META,
    "related_facilty":                           DetectedColumnRole.STRUCTURED_REF,
    "related_facility":                          DetectedColumnRole.STRUCTURED_REF,
    "connected_power_station":                   DetectedColumnRole.STRUCTURED_REF,
    "connection_to_strategic_fuel_reserves":     DetectedColumnRole.STRUCTURED_REF,
    "refined_coordinate":                        DetectedColumnRole.GEO,
    "site_by_aerial_defense":                    DetectedColumnRole.STRUCTURED_REF,
}

# ── Heuristic hint sets for unknown/generic schemas ───────────────────────────

_LOCATION_HINTS = {
    "location", "loc", "site", "site_name", "building", "base", "address",
    "facility", "zone", "segment", "מיקום", "אתר", "בסיס",
}
_FACILITY_HINTS = {"facility_name", "facility", "building_name"}
_COMPONENT_HINTS = {"component_name", "component"}
_DEPENDENCY_HINTS = {
    "dependency", "dependencies", "dep", "uses", "contains", "hosts",
    "departments", "department", "projects", "project", "assets",
    "systems", "personnel", "תלות", "תלויות", "מחלקות",
}
_DESCRIPTION_HINTS = {
    "description", "desc", "notes", "remarks", "details", "purpose",
    "details_on_facilty_purpose", "details_on_facility_purpose",
    "תיאור", "הערות",
}
_FREE_TEXT_HINTS = {
    "operational_significance_if_damaged", "sop_if_damaged",
    "system_information", "component_importance_to_system",
    "distribution_details", "redundency_details", "redundancy_details",
}
_STRUCTURED_REF_HINTS = {
    "primary_backup", "secondary_primary", "related_facilty", "related_facility",
    "connected_power_station", "connection_to_strategic_fuel_reserves",
    "responsible_body", "system", "site_by_aerial_defense",
}
_CATEGORICAL_HINTS = {
    "support_for_attack_effort", "support_for_defende_control_effort",
    "support_for_defence_control_effort", "support_for_intelligence_effort",
    "support_for_allert_effort", "support_for_alert_effort",
    "support_for_national_effort", "deffence_with_iron_dome",
    "defence_with_iron_dome", "level_for_deffense_with_upper_layer",
    "level_for_defence_with_upper_layer", "central_point",
}
_GEO_HINTS = {"ploygon", "polygon", "central_point", "refined_coordinate", "coordinate", "geo"}
_META_HINTS = {
    "region", "tier", "status", "type", "category", "criticality", "id",
    "hardering", "hardening", "concelaments", "concealment",
    "sidtibution", "distribution", "recovery_capability",
    "redundency", "redundancy", "mobility",
    "אזור", "קריטיות", "סטטוס",
}


def _detect_column_role(col_name: str, sample_values: list[str]) -> DetectedColumnRole:
    """Heuristic role detection from column name and sample values."""
    name_lower = col_name.lower().strip()

    # Check known schema first
    if name_lower in _KNOWN_SCHEMA:
        return _KNOWN_SCHEMA[name_lower]

    words = set(name_lower.replace("-", " ").replace("_", " ").split())

    if words & _LOCATION_HINTS or name_lower in _LOCATION_HINTS:
        return DetectedColumnRole.LOCATION_ID
    if words & _FACILITY_HINTS or name_lower in _FACILITY_HINTS:
        return DetectedColumnRole.FACILITY_ID
    if words & _COMPONENT_HINTS or name_lower in _COMPONENT_HINTS:
        return DetectedColumnRole.COMPONENT_ID
    if name_lower in _FREE_TEXT_HINTS:
        return DetectedColumnRole.FREE_TEXT
    if name_lower in _STRUCTURED_REF_HINTS:
        return DetectedColumnRole.STRUCTURED_REF
    if name_lower in _CATEGORICAL_HINTS:
        return DetectedColumnRole.CATEGORICAL
    if name_lower in _GEO_HINTS:
        return DetectedColumnRole.GEO
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
            return DetectedColumnRole.FREE_TEXT
        if avg_len < 20:
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

    Now recognises the known 36-column facility schema directly.
    """
    sample_rows = rows[:max_sample]
    columns: list[DetectedColumn] = []
    warnings: list[str] = []

    location_col: Optional[str] = None
    facility_col: Optional[str] = None
    component_col: Optional[str] = None
    dep_cols: list[str] = []
    free_text_cols: list[str] = []
    structured_ref_cols: list[str] = []
    categorical_cols: list[str] = []
    geo_cols: list[str] = []
    desc_cols: list[str] = []
    meta_cols: list[str] = []

    # Detect merged-cell markers (openpyxl leaves None for merged cells)
    none_counts = {h: sum(1 for r in sample_rows if r.get(h) is None) for h in headers}
    for h, cnt in none_counts.items():
        if cnt > len(sample_rows) * 0.5 and len(sample_rows) > 0:
            warnings.append(
                f"Column '{h}' has > 50% empty cells — possible merged cell or sparse data"
            )

    confidence_map: dict[str, float] = {}
    for h in headers:
        vals = [str(r[h]) for r in sample_rows if r.get(h) is not None][:5]
        role = _detect_column_role(h, vals)

        # Confidence: high for known schema columns, lower for heuristic
        h_lower = h.lower().strip()
        if h_lower in _KNOWN_SCHEMA:
            col_conf = 0.98
        elif role != DetectedColumnRole.UNKNOWN:
            col_conf = 0.85
        else:
            col_conf = 0.4

        # First column fallback
        if h == headers[0] and role == DetectedColumnRole.UNKNOWN:
            role = DetectedColumnRole.LOCATION_ID
            col_conf = 0.6

        columns.append(DetectedColumn(
            column_name=h,
            detected_role=role,
            sample_values=vals,
            confidence=col_conf,
        ))
        confidence_map[h] = col_conf

        if role == DetectedColumnRole.LOCATION_ID and location_col is None:
            location_col = h
        elif role == DetectedColumnRole.FACILITY_ID and facility_col is None:
            facility_col = h
        elif role == DetectedColumnRole.COMPONENT_ID and component_col is None:
            component_col = h
        elif role == DetectedColumnRole.FREE_TEXT:
            free_text_cols.append(h)
        elif role == DetectedColumnRole.STRUCTURED_REF:
            structured_ref_cols.append(h)
        elif role == DetectedColumnRole.CATEGORICAL:
            categorical_cols.append(h)
        elif role == DetectedColumnRole.GEO:
            geo_cols.append(h)
        elif role == DetectedColumnRole.DEPENDENCY:
            dep_cols.append(h)
        elif role == DetectedColumnRole.LOCATION_DESC:
            desc_cols.append(h)
        elif role == DetectedColumnRole.META:
            meta_cols.append(h)

    # Fallbacks
    if not location_col and headers:
        location_col = headers[0]
        warnings.append(
            f"No confident site/location column found — defaulting to '{location_col}'. "
            "Please verify in the UI before running ingestion."
        )

    if not dep_cols and not free_text_cols:
        remaining = [
            h for h in headers
            if h not in [location_col, facility_col, component_col]
            and h not in desc_cols and h not in meta_cols
            and h not in structured_ref_cols and h not in categorical_cols
            and h not in geo_cols
        ]
        if remaining:
            dep_cols = remaining
            warnings.append(
                f"No dependency/free-text columns confidently detected. "
                f"Defaulting to: {dep_cols}. Please verify."
            )

    overall_conf = min(confidence_map.values()) if confidence_map else 0.5

    return DetectedSchema(
        columns=columns,
        location_column=location_col or (headers[0] if headers else ""),
        dependency_columns=dep_cols + free_text_cols,
        description_columns=desc_cols,
        meta_columns=meta_cols + categorical_cols + geo_cols,
        total_rows=len(rows),
        sample_rows=[{k: str(v) for k, v in r.items()} for r in rows[:5]],
        detection_confidence=overall_conf,
        warnings=warnings,
    )


# ── Review Queue item ─────────────────────────────────────────────────────────

class ReviewQueueItem(BaseModel):
    """A row that could not be fully committed — queued for human review.
    No row is ever silently discarded.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str
    row_index: int
    raw_row: dict[str, Any]
    location_name: Optional[str] = None
    reason: str
    llm_extraction: Optional[FacilityRowExtractionOutput] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Excel Connector ───────────────────────────────────────────────────────────

class ExcelConnector(SourceConnector):
    """
    Source connector for Excel dependency files with unknown OR known schema.
    """

    connector_type = ConnectorType.EXCEL

    def __init__(
        self,
        file_path: str,
        connector_id: str = "excel-manual",
        llm_client: Optional[Any] = None,
        sheet_name: Optional[str | int] = 0,
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

    def _read_excel_raw(self) -> tuple[list[str], list[dict[str, Any]]]:
        """Read Excel file into headers + rows list."""
        try:
            import openpyxl
        except ImportError:
            raise ImportError(
                "openpyxl is required for ExcelConnector. "
                "Install with: pip install openpyxl"
            )

        wb = openpyxl.load_workbook(self._file_path, data_only=True)

        if self._sheet_name is None:
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
        """Schema detection pass."""
        headers, rows = self._read_excel_raw()
        schema = detect_schema_heuristic(headers, rows, max_sample=20)
        logger.info(
            f"Schema detected for '{self._file_path}': "
            f"location_col='{schema.location_column}' "
            f"confidence={schema.detection_confidence:.2f}"
        )
        return schema

    async def get_document(self, external_id: str) -> SourceDocument:
        """Fetch a single row by its external_id."""
        _, rows = self._read_excel_raw()
        idx = int(external_id.split("::row::")[-1])
        if idx >= len(rows):
            raise ValueError(f"Row index {idx} out of range")
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
        """Yield one SourceDocument per Excel row."""
        headers, rows = self._read_excel_raw()
        schema = schema_overrides or await self.detect_schema()

        loc_col = schema.location_column

        def _cols_for_role(role: DetectedColumnRole) -> list[str]:
            return [c.column_name for c in schema.columns if c.detected_role == role]

        facility_cols = _cols_for_role(DetectedColumnRole.FACILITY_ID)
        component_cols = _cols_for_role(DetectedColumnRole.COMPONENT_ID)
        free_text_cols = _cols_for_role(DetectedColumnRole.FREE_TEXT)
        structured_ref_cols = _cols_for_role(DetectedColumnRole.STRUCTURED_REF)
        categorical_cols = _cols_for_role(DetectedColumnRole.CATEGORICAL)
        geo_cols = _cols_for_role(DetectedColumnRole.GEO)
        dep_cols = _cols_for_role(DetectedColumnRole.DEPENDENCY)
        desc_cols = _cols_for_role(DetectedColumnRole.LOCATION_DESC)

        for idx, row in enumerate(rows):
            if all(v is None or str(v).strip() == "" for v in row.values()):
                continue

            external_id = f"{self._connector_id}::row::{idx}"

            def _get(col: str) -> str:
                v = row.get(col)
                return str(v).strip() if v is not None else ""

            site_name = _get(loc_col)
            facility_name = _get(facility_cols[0]) if facility_cols else ""
            component_name = _get(component_cols[0]) if component_cols else ""

            dep_text = " | ".join(_get(col) for col in dep_cols + free_text_cols if _get(col))
            
            structured_refs = {}
            for col in structured_ref_cols:
                val = _get(col)
                if val:
                    # Special handling for known array columns like connected_power_station
                    if col == "connected_power_station" and ("," in val or "\n" in val):
                        # Split by comma or newline and add as multiple entries if needed, 
                        # but our graph_ingestor currently expects a single string per dict key.
                        # For simplicity, we just pass the raw string and let the graph ingestor or downstream handle it, 
                        # OR we change the graph ingestor. Since graph ingestor expects string, we keep it as string here, 
                        # but in unstructured we pass it to LLM if needed. Actually, graph ingestor can handle lists if we 
                        # change it, but let's just use the primary element or assume it's one for now, or split it in ingestor.
                        # Leaving as is to avoid breaking existing downstream, but we pass it cleanly.
                        # We will split it in the graph ingestor directly instead.
                        pass
                    structured_refs[col] = val

            categoricals = {col: _get(col) for col in categorical_cols if _get(col)}
            free_texts = {col: _get(col) for col in free_text_cols if _get(col)}
            geos = {col: _get(col) for col in geo_cols if _get(col)}
            meta = {
                col: _get(col)
                for col in headers
                if col not in [loc_col] + facility_cols + component_cols + free_text_cols + 
                   structured_ref_cols + categorical_cols + geo_cols + dep_cols + desc_cols
                and _get(col)
            }

            review_needed = False
            review_reason = ""

            if not site_name:
                review_needed = True
                review_reason = "Missing site_name"
                self._review_queue.append(ReviewQueueItem(
                    source_file=self._file_path,
                    row_index=idx,
                    raw_row={k: str(v) for k, v in row.items()},
                    reason=review_reason,
                ))

            full_content = {
                "site_name": site_name,
                "facility_name": facility_name,
                "component_name": component_name,
                "structured_refs": structured_refs,
                "categoricals": categoricals,
                "free_texts": free_texts,
                "geos": geos,
                "meta": meta,
                "location_name": site_name,
                "dependency_text": dep_text,
                "description": " ".join(_get(col) for col in desc_cols if _get(col)),
                "raw_row": {k: str(v) for k, v in row.items() if v is not None},
                "row_index": idx,
                "review_needed": review_needed,
                "review_reason": review_reason,
            }
            content_hash = SourceDocument.compute_hash(full_content)
            title = site_name or facility_name or f"Row {idx}"

            yield SourceDocument(
                external_id=external_id,
                title=title,
                content_type="excel_row",
                raw_content=full_content,
                metadata={
                    "row_index": idx,
                    "review_needed": review_needed,
                },
                content_hash=content_hash,
                document_type="EXCEL_ROW",
                source_connector_id=self._connector_id,
                connector_type=ConnectorType.EXCEL,
            )

    @property
    def review_queue(self) -> list[ReviewQueueItem]:
        return list(self._review_queue)


# ── Facility Row Impact Extractor (LLM) ───────────────────────────────────────

class FacilityRowImpactExtractor:
    """LLM-based extractor for free-text columns."""

    _SYSTEM_PROMPT = """\
You are an expert analyst. Extract dependency edges and new entities from free-text fields.
Identify: from_entity, from_type, to_entity, to_type, edge_type, criticality, source_column, weight (0.0-1.0), and meaning.
If there are completely new systems/entities mentioned in the text that act as standalone nodes, add them to `nodes`.

CRITICAL NORMALIZATION REQUIREMENT:
Extract normalized categorical values and numerical values IN PROPORTION to the global dataset context provided below.
Ensure the semantics you extract align with the frequency and ranges of the entire dataset.

{dataset_context}

Extract normalized geographic coordinates or polygons into `geo_data`.
Rules: Extract only explicit/implied info. Use SITE|FACILITY|COMPONENT|SYSTEM types.
Form weighted edges from numerical 'support_for_x_effort' variables using 'SUPPORTS' as the edge type and assigning the weight/meaning.
Return empty edges list if nothing found."""

    def __init__(self, llm_client: Any, dataset_context: str = "") -> None:
        self._chain = llm_client.with_structured_output(FacilityRowExtractionOutput)
        self._dataset_context = dataset_context or "No global context available."

    async def extract(
        self,
        site_name: str,
        facility_name: str,
        component_name: str,
        free_texts: dict[str, str],
    ) -> FacilityRowExtractionOutput:
        from langchain_core.messages import HumanMessage, SystemMessage

        if not any(free_texts.values()):
            return FacilityRowExtractionOutput(
                facility_name=facility_name or site_name,
                edges=[],
                review_needed=False,
                confidence=1.0,
            )

        col_sections = "\n".join(f"[{col}]\n{val}" for col, val in free_texts.items() if val)
        human_content = (
            f"Site: {site_name}\nFacility: {facility_name}\nComponent: {component_name}\n\n"
            f"FIELDS:\n{col_sections}"
        )
        
        sys_prompt = self._SYSTEM_PROMPT.replace("{dataset_context}", self._dataset_context)

        try:
            result = await self._chain.ainvoke([
                SystemMessage(content=sys_prompt),
                HumanMessage(content=human_content),
            ])
            return result
        except Exception as exc:
            return FacilityRowExtractionOutput(
                facility_name=facility_name or site_name,
                edges=[],
                review_needed=True,
                review_reason=str(exc),
                confidence=0.0,
            )


class ExcelDependencyExtractor:
    """Legacy generic extractor."""
    def __init__(self, llm_client: Any) -> None:
        self._chain = llm_client.with_structured_output(ExcelDependencyExtraction)

    async def extract(self, location_name: str, dep_text: str, description: str = "") -> Any:
        from langchain_core.messages import HumanMessage, SystemMessage
        try:
            return await self._chain.ainvoke([
                SystemMessage(content="Legacy extractor"),
                HumanMessage(content=f"{location_name}: {dep_text}"),
            ])
        except Exception:
            return ExcelDependencyExtraction(location_name=location_name, entities=[], confidence=0.0)
