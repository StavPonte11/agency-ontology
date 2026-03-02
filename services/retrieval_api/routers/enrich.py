"""Enrich endpoint — extract concepts from text and inject context into agent prompts."""
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
    "/enrich",
    summary="Enrich query text with matched concept context",
    description=(
        "Extracts all organizational concepts mentioned in the query text and returns "
        "a formatted context block for injection into an agent system prompt. "
        "Supports Hebrew military terminology."
    ),
)
async def enrich(
    body: dict,
    services: dict = Depends(get_services),
):
    text: str = body.get("text", "")
    max_concepts: int = body.get("max_concepts", 10)
    max_tokens_budget: int = body.get("max_tokens_budget", 2000)

    if not text:
        return {"context_block": "", "matched_concepts": [], "no_concepts_found": True, "token_count_estimate": 0}

    embedding_svc = services["embedding"]
    es = services["es"]

    emb = await embedding_svc.embed(text[:2000])
    results = await es.hybrid_search(
        query_text=text[:500],
        query_embedding=emb,
        filters={},
        k=max_concepts * 2,
        search_mode="hybrid",
    )

    matched: list = []
    context_parts: list = []
    total_chars = 0

    for r in results[:max_concepts]:
        name = r.get("name_he") or r["name"]
        desc = r.get("description_he") or r.get("description", "")
        aliases = r.get("aliases") or []

        entry_text = f"**{name}**: {desc}"
        if aliases:
            entry_text += f" (נרדף: {', '.join(aliases[:3])})"
        entry_text += "\n"

        total_chars += len(entry_text)
        if total_chars > max_tokens_budget * 4:
            break

        context_parts.append(entry_text)
        matched.append({
            "term": name,
            "concept_id": r["concept_id"],
            "confidence": r.get("confidence", 0.7),
        })

    if not context_parts:
        return {"context_block": "", "matched_concepts": [], "no_concepts_found": True, "token_count_estimate": 0}

    context_block = (
        "## הגדרות ומושגים ארגוניים רלוונטיים / Relevant Organizational Concepts\n\n"
        + "\n".join(context_parts)
    )

    return {
        "context_block": context_block,
        "matched_concepts": matched,
        "no_concepts_found": False,
        "token_count_estimate": len(context_block) // 4,
    }
