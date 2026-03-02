"""Schema context endpoint — returns DB tables/columns for business concepts (TextToSQL)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

router = APIRouter()


def get_services(request: Request) -> dict:
    return {
        "neo4j": request.app.state.neo4j,
        "es": request.app.state.es,
        "cache": request.app.state.cache,
        "embedding": request.app.state.embedding,
        "cb": request.app.state.circuit_breakers,
    }


@router.post(
    "/schema-context",
    summary="Get database schema for business concepts (TextToSQL)",
    description=(
        "Given Hebrew or English business concept names, returns the exact database "
        "tables and columns that represent those concepts. Essential for TextToSQL agents. "
        "Always call before writing SQL queries involving business entities."
    ),
)
async def schema_context(
    body: dict,
    services: dict = Depends(get_services),
):
    concepts: list[str] = body.get("concepts", [])
    include_lineage: bool = body.get("include_lineage", False)
    # TODO(permissions): Filter schema results by agent's DB access permissions.

    if not concepts:
        return {"tables": [], "unmapped_concepts": []}

    neo4j = services["neo4j"]
    tables, unmapped = await neo4j.get_schema_context(concepts)
    return {"tables": tables, "unmapped_concepts": unmapped}
