"""
Impact Analysis FastAPI Router — Agency Ontology
================================================
6 MCP tool endpoints implementing the impact propagation API:

  POST /v1/impact/propagate   — impact_propagate
  POST /v1/impact/reverse     — impact_reverse_query
  POST /v1/impact/compare     — impact_compare_locations
  POST /v1/impact/mitigations — impact_find_mitigations
  POST /v1/impact/historical  — impact_historical_context
  POST /v1/impact/scenario    — impact_scenario_model
  GET  /v1/impact/coverage    — data quality metrics

All endpoints:
  - Return HTTP 404 with closest_candidates for unknown entities
  - Support degraded mode (error dict) when Neo4j is down
  - Generate situation reports only when explicitly requested
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from services.pipeline.models.ontology import (
    DisruptionType,
    ImpactCompareRequest,
    ImpactHistoricalRequest,
    ImpactMitigationsRequest,
    ImpactPropagateRequest,
    ImpactReverseRequest,
)
from services.retrieval_api.services.impact_service import ImpactService

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Dependencies ──────────────────────────────────────────────────────────────

async def get_impact_service(request: Request) -> ImpactService:
    """Retrieve ImpactService from app.state (initialized in lifespan)."""
    impact: ImpactService | None = getattr(request.app.state, "impact", None)
    if impact is None:
        raise HTTPException(
            status_code=503,
            detail="Impact service not initialized — check Neo4j connection",
        )
    return impact


def _closest_candidates_from_neo4j(entity_name: str) -> list[str]:
    """
    Placeholder — real implementation queries Neo4j fulltext index.
    Returns approximate candidates for unknown entity names.
    """
    # TODO: wire Neo4jService.lookup_concept here in a future iteration
    return []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/impact/propagate")
async def propagate_impact(
    request_body: ImpactPropagateRequest,
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Primary impact propagation endpoint (MCP tool: impact_propagate).

    Traverses the dependency graph from the trigger entity and returns
    all affected entities tiered as CRITICAL / HIGH / MONITOR.

    Pre-operational halt: PLANNED/SUSPENDED projects stop severity propagation
    in the Cypher WHERE clause — their downstream clients are not reached.
    """
    logger.info(
        f"impact/propagate: entity={request_body.entity_name!r} "
        f"disruption={request_body.disruption_type.value} "
        f"depth={request_body.max_depth}"
    )

    result = await impact.propagate_impact(
        entity_name=request_body.entity_name,
        disruption_type=request_body.disruption_type,
        max_depth=request_body.max_depth,
        include_mitigation=request_body.include_mitigation,
        include_historical=request_body.include_historical,
        is_simulation=False,
    )

    # Return 404 if coverage is 0 and no entities found (unknown trigger)
    if (
        result.coverage_confidence == 0.0
        and result.total_affected == 0
        and request_body.entity_name in result.low_coverage_entities
    ):
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Entity '{request_body.entity_name}' not found in impact graph",
                "closest_candidates": _closest_candidates_from_neo4j(request_body.entity_name),
            },
        )

    return result.model_dump(mode="json")


@router.post("/impact/reverse")
async def reverse_query(
    request_body: ImpactReverseRequest,
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Reverse dependency query (MCP tool: impact_reverse_query).
    Answers: "What depends on this entity? Who would break if it disappeared?"
    """
    logger.info(f"impact/reverse: entity={request_body.entity_name!r}")

    result = await impact.reverse_query(
        entity_name=request_body.entity_name,
        entity_type=request_body.entity_type,
        max_depth=request_body.max_depth,
    )

    if not result.get("dependent_entities") and "error" not in result:
        result["message"] = (
            f"No entities found that depend on '{request_body.entity_name}'. "
            "This may mean the entity has no upstream dependencies, or it is not in the graph."
        )

    return result


@router.post("/impact/compare")
async def compare_locations(
    request_body: ImpactCompareRequest,
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Multi-location blast radius comparison (MCP tool: impact_compare_locations).
    Returns ranked list of locations by specified metric.
    """
    logger.info(
        f"impact/compare: locations={request_body.location_names} "
        f"metric={request_body.metric}"
    )

    ranked = await impact.compare_locations(
        location_names=request_body.location_names,
        metric=request_body.metric,
    )

    return {
        "metric": request_body.metric,
        "ranked_locations": ranked,
        "total_compared": len(ranked),
    }


@router.post("/impact/mitigations")
async def find_mitigations(
    request_body: ImpactMitigationsRequest,
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Mitigation options retrieval (MCP tool: impact_find_mitigations).
    Retrieves all documented mitigation options for an affected entity.
    """
    logger.info(f"impact/mitigations: entity={request_body.entity_name!r}")

    options = await impact.find_mitigations(
        entity_name=request_body.entity_name,
        scenario_context=request_body.scenario_context,
    )

    return {
        "entity_name": request_body.entity_name,
        "mitigation_options": [m.model_dump() for m in options],
        "total_options": len(options),
        "has_backup": any(o.option_type in ("backup_location", "redundant_asset") for o in options),
    }


@router.post("/impact/historical")
async def historical_context(
    request_body: ImpactHistoricalRequest,
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Historical incident retrieval (MCP tool: impact_historical_context).
    Returns past incidents involving the specified entities or locations.
    """
    logger.info(
        f"impact/historical: entities={request_body.entity_names} "
        f"locations={request_body.location_names}"
    )

    if not request_body.entity_names and not request_body.location_names:
        raise HTTPException(
            status_code=422,
            detail="At least one of entity_names or location_names must be provided",
        )

    incidents = await impact.get_historical_context(
        entity_names=request_body.entity_names,
        location_names=request_body.location_names,
        since_date=request_body.since_date,
    )

    return {
        "incidents": [i.model_dump(mode="json") for i in incidents],
        "total_incidents": len(incidents),
        "query": {
            "entity_names": request_body.entity_names,
            "location_names": request_body.location_names,
            "since_date": request_body.since_date,
        },
    }


@router.post("/impact/scenario")
async def scenario_model(
    request_body: ImpactPropagateRequest,
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Hypothetical scenario modelling (MCP tool: impact_scenario_model).

    Identical to /impact/propagate but:
    - No state is written to the graph
    - Every section of the output is labeled [SIMULATION]
    - The is_simulation flag is True throughout
    """
    logger.info(
        f"impact/scenario: entity={request_body.entity_name!r} "
        f"[SIMULATION]"
    )

    result = await impact.propagate_impact(
        entity_name=request_body.entity_name,
        disruption_type=request_body.disruption_type,
        max_depth=request_body.max_depth,
        include_mitigation=request_body.include_mitigation,
        include_historical=request_body.include_historical,
        is_simulation=True,  # key difference — always True
    )

    result_dict = result.model_dump(mode="json")
    result_dict["simulation_note"] = (
        "[SIMULATION] This is a hypothetical scenario — no graph state was modified. "
        "Results reflect current data as of this query."
    )
    return result_dict


@router.get("/impact/coverage")
async def get_coverage(
    impact: ImpactService = Depends(get_impact_service),
) -> dict[str, Any]:
    """
    Data quality / coverage metrics for the Impact Dashboard.
    Returns: total_locations, locations_with_deps, coverage_score (%), target.
    """
    return await impact.get_coverage_metrics()
