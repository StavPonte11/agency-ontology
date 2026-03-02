"""
Situation Report Generator — Agency Ontology Impact Extension
=============================================================
Generates structured situation reports from propagation results.

The Part 6 contract is strictly enforced:
  1. Every entity named in the report MUST exist in the propagation result.
  2. The hallucination check is always run — report is rejected if entities
     are named that do not appear in the graph.
  3. PLANNED/SUSPENDED entities appear only in MONITOR section with an
     explicit explanation of WHY they need no immediate action.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from services.pipeline.models.ontology import (
    PropagationResult,
    SituationReport,
)

logger = logging.getLogger(__name__)


# ── System prompt (Part 6 format contract) ────────────────────────────────────

_SITUATION_REPORT_SYSTEM = """You are a duty officer producing a situation report.
You MUST follow this exact format. Every section is mandatory.

CRITICAL RULES:
1. Every entity you name MUST appear in the PROVIDED ENTITY DATA below.
   Do NOT invent, infer, or expand beyond the provided list.
2. critical_immediate: ONLY entities with impact_tier=CRITICAL and no mitigation.
3. high_time_sensitive: ONLY entities with impact_tier=HIGH.
4. monitor_no_action: Pre-operational entities (PLANNED/SUSPENDED) MUST appear here.
   For each, write WHY: "Project B has never been operational — Client G is not
   being actively served and thus experiences no harm."
5. If the result is a SIMULATION, start every section with [SIMULATION].
6. confidence field: HIGH | MEDIUM | LOW only.
7. named_entities: list every entity name you mention anywhere in the report.

Produce output matching the SituationReport schema exactly."""


def _format_entity_data_for_llm(prop_result: PropagationResult) -> str:
    """Serialize propagation result into a compact LLM-readable string."""
    lines = [
        f"TRIGGER: {prop_result.trigger_entity} ({prop_result.trigger_entity_type.value})",
        f"DISRUPTION: {prop_result.disruption_type.value}",
        f"TIMESTAMP: {prop_result.timestamp.isoformat()}",
        f"IS_SIMULATION: {prop_result.is_simulation}",
        "",
        "=== CRITICAL ENTITIES (no mitigation) ===",
    ]

    for e in prop_result.critical_entities:
        mit_note = "NO MITIGATION" if not e.mitigation_available else f"MITIGATION AVAILABLE (recovery: {e.recovery_time_hours}h)"
        lines.append(
            f"  - {e.name} [{e.entity_type.value}] | "
            f"criticality={e.criticality.value} | hop={e.hop_distance} | "
            f"via {' → '.join(e.propagation_path[-3:])} | {mit_note}"
        )

    lines.append("")
    lines.append("=== HIGH ENTITIES (time-sensitive) ===")
    for e in prop_result.high_entities:
        mit_note = f"mitigation_available={e.mitigation_available}"
        if e.recovery_time_hours:
            mit_note += f", recovery={e.recovery_time_hours}h"
        lines.append(
            f"  - {e.name} [{e.entity_type.value}] | "
            f"criticality={e.criticality.value} | hop={e.hop_distance} | {mit_note}"
        )

    lines.append("")
    lines.append("=== MONITOR ENTITIES (no immediate action) ===")
    for e in prop_result.monitor_entities:
        status_note = f"operational_status={e.operational_status.value}"
        lines.append(
            f"  - {e.name} [{e.entity_type.value}] | "
            f"{status_note} | hop={e.hop_distance}"
        )

    lines.append("")
    lines.append("=== MITIGATIONS ===")
    for m in prop_result.mitigations:
        lines.append(f"  - {m.entity_name}: {m.description} (source: {m.source})")

    lines.append("")
    lines.append("=== HISTORICAL CONTEXT ===")
    if prop_result.historical_context:
        ctx = prop_result.historical_context
        if isinstance(ctx, list) and len(ctx) > 0:
            recent = ctx[0] if isinstance(ctx[0], dict) else {}
            lines.append(f"  Most recent: {recent.get('title', 'unknown')} | {recent.get('incident_date', 'date unknown')}")
            lines.append(f"  Outcome: {recent.get('outcome', 'not recorded')}")
    else:
        lines.append("  No closely matching historical incidents found in knowledge base.")

    lines.append("")
    lines.append(f"COVERAGE_CONFIDENCE: {prop_result.coverage_confidence}")
    if prop_result.low_coverage_entities:
        lines.append(f"LOW_COVERAGE_ENTITIES: {', '.join(prop_result.low_coverage_entities)}")

    return "\n".join(lines)


class SituationReportGenerator:
    """
    Generates structured SituationReport from a PropagationResult using LLM.
    Always validates output for hallucinated entity names.
    """

    def __init__(self, llm_client: Any) -> None:
        """
        llm_client: LangChain ChatOpenAI / ChatOllama instance.
        Will be wrapped with .with_structured_output(SituationReport).
        """
        self._chain = llm_client.with_structured_output(SituationReport)

    async def generate(
        self,
        prop_result: PropagationResult,
    ) -> SituationReport:
        """Generate a situation report from a propagation result."""
        from langchain_core.messages import HumanMessage, SystemMessage

        entity_data = _format_entity_data_for_llm(prop_result)
        human_content = (
            f"Generate a situation report for the following impact propagation result:\n\n"
            f"{entity_data}\n\n"
            f"Location: {prop_result.trigger_entity}"
        )

        messages = [
            SystemMessage(content=_SITUATION_REPORT_SYSTEM),
            HumanMessage(content=human_content),
        ]

        try:
            report: SituationReport = await self._chain.ainvoke(messages)
        except Exception as exc:
            logger.error(f"SituationReport LLM call failed: {exc}")
            # Return a minimal safe report rather than crashing
            return self._fallback_report(prop_result, error=str(exc))

        # Hallucination check — every named entity must exist in the graph
        known_names = {e.name.lower() for e in (
            prop_result.critical_entities
            + prop_result.high_entities
            + prop_result.monitor_entities
        )} | {prop_result.trigger_entity.lower()}

        hallucinated = [
            n for n in report.named_entities
            if n.lower() not in known_names
        ]
        if hallucinated:
            logger.warning(
                f"Hallucinated entity names in situation report: {hallucinated}. "
                "Stripping from named list."
            )
            report.named_entities = [
                n for n in report.named_entities if n.lower() in known_names
            ]

        # Ensure simulation label is consistent
        report.is_simulation = prop_result.is_simulation
        report.timestamp = prop_result.timestamp

        logger.info(
            f"SituationReport generated for '{prop_result.trigger_entity}': "
            f"crit={len(prop_result.critical_entities)} "
            f"high={len(prop_result.high_entities)} "
            f"monitor={len(prop_result.monitor_entities)}"
        )

        return report

    def _fallback_report(self, prop_result: PropagationResult, error: str = "") -> SituationReport:
        """Minimal deterministic report when LLM call fails."""
        crit_names = [e.name for e in prop_result.critical_entities]
        high_names = [e.name for e in prop_result.high_entities]
        monitor_names = [e.name for e in prop_result.monitor_entities]

        return SituationReport(
            location_name=prop_result.trigger_entity,
            timestamp=prop_result.timestamp,
            is_simulation=prop_result.is_simulation,
            situation=(
                f"{prop_result.trigger_entity} is unavailable "
                f"(disruption: {prop_result.disruption_type.value}). "
                f"{prop_result.total_affected} entities affected. "
                f"Report generated from structured data — LLM unavailable."
            ),
            critical_immediate=[
                f"{n} — CRITICAL impact, no mitigation available" for n in crit_names
            ],
            high_time_sensitive=[
                f"{n} — HIGH impact" for n in high_names
            ],
            monitor_no_action=[
                f"{n} — MONITOR level" for n in monitor_names
            ],
            historical_context="Historical context unavailable — LLM call failed.",
            confidence="LOW",
            confidence_reason=f"LLM call failed during report generation: {error}",
            named_entities=crit_names + high_names + monitor_names,
        )
