"""Feedback endpoint — agents report ontology quality issues for human review."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
log = logging.getLogger(__name__)


@router.post(
    "/feedback",
    summary="Submit ontology quality feedback",
    description=(
        "Report incorrect, incomplete, or misleading ontology entries. "
        "Call when retrieved information led to a wrong output, a definition is incorrect, "
        "a term is missing, or a data mapping is wrong. "
        "This feedback directly improves the ontology for all agents."
    ),
)
async def feedback(body: dict, request: Request):
    concept_id: str | None = body.get("concept_id")
    feedback_type: str | None = body.get("feedback_type")

    if not concept_id or not feedback_type:
        raise HTTPException(status_code=422, detail="concept_id and feedback_type are required")

    feedback_id = str(uuid.uuid4())

    # Publish feedback event to Kafka (fire-and-forget)
    try:
        from services.pipeline.kafka.client import get_publisher  # type: ignore[import]
        publisher = get_publisher()
        publisher.publish(
            topic="agency.ontology.feedback",
            key=concept_id,
            value={
                "feedback_id": feedback_id,
                "concept_id": concept_id,
                "feedback_type": feedback_type,
                "agent_id": body.get("agent_id"),
                "session_id": body.get("session_id"),
                "trace_id": body.get("trace_id"),
                "context": body.get("context"),
                "notes": body.get("notes"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        log.warning("Failed to publish feedback to Kafka: %s", exc)

    return {"acknowledged": True, "feedback_id": feedback_id}
