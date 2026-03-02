"""Search endpoint — hybrid BM25 + kNN vector search over the ontology graph."""
from __future__ import annotations

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter()


def get_services(request: Request) -> dict:
    return {
        "neo4j": request.app.state.neo4j,
        "es": request.app.state.es,
        "cache": request.app.state.cache,
        "embedding": request.app.state.embedding,
        "cb": request.app.state.circuit_breakers,
    }


@router.get(
    "/search",
    summary="Search concepts (lexical + semantic + hybrid)",
    description=(
        "Search the organizational knowledge graph. Supports Hebrew and English queries. "
        "Hebrew queries are analyzed with nikud-stripping. "
        "Default mode: hybrid (BM25 + kNN RRF fusion)."
    ),
)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    concept_types: Optional[str] = None,  # comma-separated ConceptType values
    domains: Optional[str] = None,        # comma-separated domain strings
    status: Optional[str] = None,
    confidence_min: Optional[float] = None,
    has_data_assets: Optional[bool] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    search_mode: str = "hybrid",
    services: dict = Depends(get_services),
):
    es = services["es"]
    embedding = services["embedding"]
    cache = services["cache"]

    filters: dict = {}
    if concept_types:
        filters["concept_types"] = [t.strip() for t in concept_types.split(",")]
    if domains:
        filters["domains"] = [d.strip() for d in domains.split(",")]
    if status:
        filters["status"] = [s.strip() for s in status.split(",")]
    if confidence_min is not None:
        filters["confidence_min"] = confidence_min

    # TODO(permissions): Add sensitivity filter based on agent clearance.

    cache_key = f"ontology:search:{q}:{search_mode}:{limit}:{offset}:{concept_types}:{domains}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    query_embedding: list = []
    if search_mode in ("semantic", "hybrid"):
        text_hash = embedding.text_hash(q)
        query_embedding = await cache.get_embedding(text_hash, embedding._model) or []
        if not query_embedding:
            query_embedding = await embedding.embed(q)
            await cache.set_embedding(text_hash, embedding._model, query_embedding)

    results = await es.hybrid_search(
        query_text=q,
        query_embedding=query_embedding,
        filters=filters,
        k=limit + offset,
        search_mode=search_mode,
    )

    page = results[offset : offset + limit]
    response = {
        "results": [
            {
                "concept": {
                    "id": r["concept_id"],
                    "name": r.get("name_he") or r["name"],
                    "concept_type": r["concept_type"],
                    "domain": r.get("domain") or [],
                },
                "description": r.get("description_he") or r.get("description", ""),
                "aliases": r.get("aliases") or [],
                "score": r.get("_score", 1.0),
                "match_type": search_mode,
            }
            for r in page
        ],
        "total": len(results),
        "query": q,
        "search_mode": search_mode,
    }

    await cache.set(cache_key, response, ttl=60)
    return response
