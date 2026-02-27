"""Lookup endpoint — primary agent-facing term resolution."""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request

router = APIRouter()


def get_services(request: Request):
    return {
        "neo4j": request.app.state.neo4j,
        "es": request.app.state.es,
        "cache": request.app.state.cache,
        "embedding": request.app.state.embedding,
        "cb": request.app.state.circuit_breakers,
    }


@router.get(
    "/lookup",
    summary="Look up an organizational term (Hebrew or English)",
    description=(
        "Primary agent endpoint. Resolves any organizational term — Hebrew military "
        "terminology, codenames, abbreviations, system names — to its canonical definition, "
        "aliases, related concepts, and data asset mappings.\n\n"
        "Hebrew terms (including nikud) are matched after normalization. "
        "Military abbreviations (ר\"מ, מפ\"ג) are matched via alias index."
    ),
)
async def lookup(
    term: Annotated[str, Query(min_length=1, max_length=500, description="Term to look up (Hebrew or English)")],
    context: Annotated[str | None, Query(max_length=2000)] = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    max_hops: Annotated[int, Query(ge=1, le=5)] = 2,
    include_data_assets: bool = True,
    services: dict = Depends(get_services),
):
    # TODO(permissions): Extract agent permission context from request headers.
    # Pass to neo4j_service.lookup_concept() to filter by sensitivity level.

    cache = services["cache"]
    neo4j = services["neo4j"]
    es = services["es"]
    embedding = services["embedding"]
    cb = services["cb"]

    # Check cache first
    cache_key = cache.lookup_key(term, max_hops)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Try Neo4j (primary)
    neo4j_cb = cb.get("neo4j")
    if neo4j_cb.allow_request():
        try:
            result = await neo4j.lookup_concept(
                term=term,
                max_hops=max_hops,
                include_data_assets=include_data_assets,
            )
            neo4j_cb.record_success()

            # Cache successful lookups
            if result.found:
                result_dict = result.model_dump(mode="json")
                await cache.set(cache_key, result_dict, ttl=300)
                return result_dict
            else:
                # Not found in Neo4j — try ES semantic search for candidates
                try:
                    emb = await embedding.embed(term)
                    es_results = await es.hybrid_search(
                        query_text=term,
                        query_embedding=emb,
                        filters={},
                        k=5,
                        search_mode="hybrid",
                    )
                    from ..models import ConceptRef, ConceptType, NotFoundResult
                    candidates = [
                        ConceptRef(
                            id=r["concept_id"],
                            name=r.get("name_he") or r["name"],
                            concept_type=ConceptType(r["concept_type"]),
                            domain=r.get("domain") or [],
                        )
                        for r in es_results
                    ]
                    not_found = NotFoundResult(
                        found=False,
                        closest_candidates=candidates,
                        degraded_mode=False,
                    )
                    return not_found.model_dump(mode="json")
                except Exception:
                    return result.model_dump(mode="json")

        except Exception as exc:
            neo4j_cb.record_failure()
            # Fallback to ES-only degraded mode
            import logging
            logging.getLogger(__name__).warning(f"Neo4j lookup failed, using ES fallback: {exc}")
    else:
        import logging
        logging.getLogger(__name__).warning("Neo4j circuit OPEN — using Elasticsearch fallback")

    # Degraded mode: ES-only lookup
    try:
        es_cb = cb.get("elasticsearch")
        if es_cb.allow_request():
            emb = await embedding.embed(term)
            es_results = await es.hybrid_search(
                query_text=term, query_embedding=emb,
                filters={}, k=1, search_mode="hybrid",
            )
            if es_results:
                r = es_results[0]
                from ..models import LookupResult, ConceptRef, ConceptType
                result = LookupResult(
                    found=True,
                    concept=ConceptRef(
                        id=r["concept_id"],
                        name=r.get("name_he") or r["name"],
                        concept_type=ConceptType(r["concept_type"]),
                        domain=r.get("domain") or [],
                    ),
                    definition=r.get("description_he") or r.get("description", ""),
                    aliases=[],
                    related=[],
                    data_assets=[],
                    confidence=r.get("confidence", 0.7),
                    degraded_mode=True,
                    degraded_reason="Neo4j unavailable — serving from Elasticsearch cache",
                )
                return result.model_dump(mode="json")
            es_cb.record_success()
    except Exception as exc:
        pass

    from ..models import NotFoundResult
    return NotFoundResult(
        found=False, closest_candidates=[], degraded_mode=True
    ).model_dump(mode="json")
