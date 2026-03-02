"""
Lookup & Hierarchy endpoints — primary agent-facing term resolution.

Endpoints:
  GET /lookup               — resolve a term, return enriched LookupResult
  GET /concepts/{id}/hierarchy — full hierarchy tree for a concept (class + ancestors + children)
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.pipeline.models.ontology import (
    ConceptRef,
    ConceptType,
    HierarchyPathStep,
    MultilingualLabel,
    StatementValue,
    LookupResult,
    NotFoundResult,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Dependency ──────────────────────────────────────────────────────────────

def get_services(request: Request) -> dict:
    return {
        "neo4j":    request.app.state.neo4j,
        "es":       request.app.state.es,
        "cache":    request.app.state.cache,
        "embedding": request.app.state.embedding,
        "cb":       request.app.state.circuit_breakers,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────

def _concept_ref_from_es(r: dict[str, Any]) -> ConceptRef:
    return ConceptRef(
        id=r["concept_id"],
        name=r.get("name_he") or r["name"],
        concept_type=ConceptType(r["concept_type"]),
        domain=r.get("domain") or [],
    )


async def _enrich_with_hierarchy(
    result: LookupResult,
    concept_id: str,
    neo4j,
) -> LookupResult:
    """
    Populate hierarchy fields on a found LookupResult:
     - ancestor_path (nearest-first)
     - subclasses + instances (if is_class)
     - multilingual_labels
     - statements
     - inherited_context (~500 token budget)

    Errors are swallowed — hierarchy enrichment is best-effort
    so it never breaks a core lookup.
    """
    try:
        # 1. Ancestor path
        ancestors_raw = await neo4j.get_ancestors(concept_id)
        ancestor_path = [
            HierarchyPathStep(
                concept_id=a["concept_id"],
                concept_name=a["concept_name"],
                relation=a["relation"],
            )
            for a in ancestors_raw
        ]
        result.ancestor_path = ancestor_path

        # 2. Children (subclasses / instances)  — only if concept is a class
        if result.is_class:
            children = await neo4j.get_children(concept_id)
            result.subclasses = [
                ConceptRef(id=c["id"], name=c["name"],
                           concept_type=ConceptType(c["concept_type"]) if c.get("concept_type") else ConceptType.TERM,
                           domain=c.get("domain") or [])
                for c in children.get("subclasses", [])
            ]
            result.instances = [
                ConceptRef(id=c["id"], name=c["name"],
                           concept_type=ConceptType(c["concept_type"]) if c.get("concept_type") else ConceptType.TERM,
                           domain=c.get("domain") or [])
                for c in children.get("instances", [])
            ]

        # 3. Multilingual labels
        labels_raw = await neo4j.get_multilingual_labels(concept_id)
        result.multilingual_labels = [
            MultilingualLabel(
                language=l["language"],
                label=l["label"],
                description=l.get("description"),
                aliases=l.get("aliases") or [],
            )
            for l in labels_raw
        ]

        # 4. Statements (inception, parent_unit, etc.)
        stmts_raw = await neo4j.get_statements(concept_id)
        result.statements = [
            StatementValue(
                property_id=s["property_id"],
                property_label=s["property_label"],
                value_type=s.get("value_type", "string"),
                string_value=s.get("value"),
                confidence=s.get("confidence", 0.8),
            )
            for s in stmts_raw
        ]

        # 5. Inherited context (assembled from ancestor descriptions)
        result.inherited_context = await neo4j.assemble_inherited_context(
            concept_id=concept_id,
            ancestor_path=[{"concept_id": a.concept_id, "concept_name": a.concept_name} for a in ancestor_path],
        )

    except Exception as exc:
        logger.warning(f"Hierarchy enrichment failed for concept {concept_id}: {exc}")

    return result


# ── GET /lookup ──────────────────────────────────────────────────────────────

@router.get(
    "/lookup",
    summary="Look up an organizational term (Hebrew or English)",
    description=(
        "Primary agent endpoint. Resolves any organizational term — Hebrew military "
        "terminology, codenames, abbreviations, system names — to its canonical definition, "
        "aliases, related concepts, data asset mappings, and **full hierarchy context**.\n\n"
        "Hierarchy enrichment adds:\n"
        "- `ancestor_path`: chain of parent classes (INSTANCE_OF / SUBCLASS_OF)\n"
        "- `inherited_context`: assembled context string from ancestor descriptions (~500 tokens)\n"
        "- `multilingual_labels`: per-language names and aliases\n"
        "- `statements`: structured facts (inception, parent_unit, location…)\n\n"
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
    include_hierarchy: bool = True,
    services: dict = Depends(get_services),
):
    """
    Resolve a term to its canonical ontology entry.

    Returns LookupResult (found=True) or NotFoundResult (found=False).
    When include_hierarchy=True (default), hierarchical enrichment is added to the result.
    """
    cache = services["cache"]
    neo4j  = services["neo4j"]
    es     = services["es"]
    embedding = services["embedding"]
    cb     = services["cb"]

    # Build a cache key that accounts for hierarchy flag
    cache_key = cache.lookup_key(term, max_hops) + (":hier" if include_hierarchy else "")
    cached = await cache.get(cache_key)
    if cached:
        logger.debug(f"Cache hit for term={term!r}")
        return cached

    # ── Primary path: Neo4j ──────────────────────────────────────────────────
    neo4j_cb = cb.get("neo4j")
    if neo4j_cb.allow_request():
        try:
            result = await neo4j.lookup_concept(
                term=term,
                max_hops=max_hops,
                include_data_assets=include_data_assets,
            )
            neo4j_cb.record_success()

            if result.found:
                concept_id = result.concept.id if result.concept else None

                # ── Hierarchy enrichment ──────────────────────────────────
                if include_hierarchy and concept_id:
                    result = await _enrich_with_hierarchy(result, concept_id, neo4j)

                result_dict = result.model_dump(mode="json")
                await cache.set(cache_key, result_dict, ttl=300)
                logger.info(f"Lookup OK: term={term!r} concept={result.concept.name if result.concept else 'N/A'} ancestors={len(result.ancestor_path)}")
                return result_dict
            else:
                # Not found in Neo4j — semantic candidates from ES
                try:
                    emb = await embedding.embed(term)
                    es_results = await es.hybrid_search(
                        query_text=term, query_embedding=emb,
                        filters={}, k=5, search_mode="hybrid",
                    )
                    candidates = [_concept_ref_from_es(r) for r in es_results]
                    not_found = NotFoundResult(found=False, closest_candidates=candidates, degraded_mode=False)
                    return not_found.model_dump(mode="json")
                except Exception:
                    return result.model_dump(mode="json")

        except Exception as exc:
            neo4j_cb.record_failure()
            logger.warning(f"Neo4j lookup failed, using ES fallback: {exc}")
    else:
        logger.warning("Neo4j circuit OPEN — using Elasticsearch fallback")

    # ── Degraded mode: Elasticsearch only ───────────────────────────────────
    try:
        es_cb = cb.get("elasticsearch")
        if es_cb.allow_request():
            emb = await embedding.embed(term)
            es_results = await es.hybrid_search(
                query_text=term, query_embedding=emb, filters={}, k=1, search_mode="hybrid",
            )
            if es_results:
                r = es_results[0]
                result = LookupResult(
                    found=True,
                    concept=_concept_ref_from_es(r),
                    definition=r.get("description_he") or r.get("description", ""),
                    aliases=[],
                    related=[],
                    data_assets=[],
                    confidence=r.get("confidence", 0.7),
                    # Hierarchy from ES pre-computed fields
                    is_class=r.get("is_class", False),
                    is_deprecated=r.get("is_deprecated", False),
                    ancestor_path=[],   # Live traversal not possible without Neo4j
                    inherited_context=None,
                    degraded_mode=True,
                    degraded_reason="Neo4j unavailable — serving from Elasticsearch cache",
                )
                es_cb.record_success()
                return result.model_dump(mode="json")
    except Exception as exc:
        logger.error(f"Elasticsearch degraded lookup also failed: {exc}")

    return NotFoundResult(found=False, closest_candidates=[], degraded_mode=True).model_dump(mode="json")


# ── GET /concepts/{concept_id}/hierarchy ────────────────────────────────────

@router.get(
    "/concepts/{concept_id}/hierarchy",
    summary="Full hierarchy tree for a concept",
    description=(
        "Returns the complete hierarchical picture for a concept:\n"
        "- `ancestors`: full ancestor chain up to root (nearest-first)\n"
        "- `subclasses`: direct subclasses (if concept is a class)\n"
        "- `instances`: direct instances (if concept is a class)\n"
        "- `siblings`: sibling concepts sharing the same parent class\n"
        "- `multilingual_labels`: all language variants\n"
        "- `statements`: structured property-value facts\n"
        "- `inherited_context`: assembled context from ancestor descriptions\n\n"
        "Use this endpoint when you need the full taxonomic picture.\n"
        "Use `/lookup` when you just want a term resolved with enrichment embedded."
    ),
)
async def get_hierarchy(
    concept_id: str,
    services: dict = Depends(get_services),
):
    """
    Return the complete hierarchy information for a concept by its ID.
    Raises HTTP 404 if the concept is not found in Neo4j.
    """
    neo4j = services["neo4j"]

    # Verify concept exists
    desc = await neo4j.get_concept_description(concept_id)
    if not desc:
        raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found in the ontology.")

    # Gather all hierarchy data in parallel
    import asyncio
    ancestors_coro  = neo4j.get_ancestors(concept_id)
    children_coro   = neo4j.get_children(concept_id)
    siblings_coro   = neo4j.get_siblings(concept_id)
    labels_coro     = neo4j.get_multilingual_labels(concept_id)
    stmts_coro      = neo4j.get_statements(concept_id)

    ancestors_raw, children, siblings, labels_raw, stmts_raw = await asyncio.gather(
        ancestors_coro, children_coro, siblings_coro, labels_coro, stmts_coro
    )

    ancestor_path = [
        {"concept_id": a["concept_id"], "concept_name": a["concept_name"], "relation": a["relation"]}
        for a in ancestors_raw
    ]

    inherited_context = await neo4j.assemble_inherited_context(
        concept_id=concept_id,
        ancestor_path=ancestor_path,
    )

    return {
        "concept_id":        concept_id,
        "name":              desc["name"],
        "description":       desc["description"],
        "ancestors":         ancestor_path,
        "subclasses":        children.get("subclasses", []),
        "instances":         children.get("instances", []),
        "siblings":          siblings,
        "multilingual_labels": labels_raw,
        "statements":        stmts_raw,
        "inherited_context": inherited_context,
    }
