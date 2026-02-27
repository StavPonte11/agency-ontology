"""
Kafka topic definitions for the Agency Ontology pipeline.
All topic metadata is centralized here — partitions, replication, retention.

Partition key strategy:
- EXTRACT, LLM_EXTRACT, NORMALIZE, COMMIT → key = document_id
  Guarantees all events for one document are processed in order by the same consumer.
- SOURCE_SCAN, INDEX_UPDATE → key = connector_id
- FEEDBACK → key = concept_id
- DLQ → key = original_topic:original_partition
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class KafkaTopic:
    name: str
    partitions: int
    replication_factor: int
    retention_ms: int              # -1 = infinite (keep forever for replay)
    cleanup_policy: str            # "delete" | "compact"
    description: str = ""         # Documentation only


TOPICS: dict[str, KafkaTopic] = {
    # ── Stage 1: Source scanning ─────────────────────────────────────────────
    # One message per connector scan run. Triggers document enumeration.
    "SOURCE_SCAN": KafkaTopic(
        name="agency.ontology.source-scan",
        partitions=3,
        replication_factor=1,        # 3 in production
        retention_ms=-1,             # Keep forever — replay scans
        cleanup_policy="delete",
        description="Source connector scan triggers. Partition key: connector_id.",
    ),
    # ── Stage 2: Per-document extraction ────────────────────────────────────
    # One message per source document to extract.
    # HIGH PARALLELISM — most CPU-bound stage (PDF parsing, OCR).
    # ⚠ INFINITE RETENTION — required for Kafka replay on prompt improvements.
    "EXTRACT": KafkaTopic(
        name="agency.ontology.extract",
        partitions=12,
        replication_factor=1,        # 3 in production
        retention_ms=-1,             # ⚠ DO NOT CHANGE — replay capability
        cleanup_policy="delete",
        description="Document extraction triggers. Partition key: document_id.",
    ),
    # ── Stage 3: LLM extraction ──────────────────────────────────────────────
    # Rate-limited by LLM inference capacity.
    # ⚠ INFINITE RETENTION — required for replay when prompts are improved.
    "LLM_EXTRACT": KafkaTopic(
        name="agency.ontology.llm-extract",
        partitions=6,
        replication_factor=1,        # 3 in production
        retention_ms=-1,             # ⚠ DO NOT CHANGE — replay capability
        cleanup_policy="delete",
        description="LLM extraction input chunks. Partition key: document_id.",
    ),
    # ── Stage 4: Normalization / entity resolution ───────────────────────────
    "NORMALIZE": KafkaTopic(
        name="agency.ontology.normalize",
        partitions=12,
        replication_factor=1,
        retention_ms=7 * 24 * 3600 * 1000,   # 7 days
        cleanup_policy="delete",
        description="Normalized extraction output. Partition key: document_id.",
    ),
    # ── Stage 5a: Commit to graph ────────────────────────────────────────────
    "COMMIT": KafkaTopic(
        name="agency.ontology.commit",
        partitions=6,
        replication_factor=1,
        retention_ms=7 * 24 * 3600 * 1000,   # 7 days
        cleanup_policy="delete",
        description="Graph commit events. Partition key: document_id.",
    ),
    # ── Stage 5b: Human review queue ─────────────────────────────────────────
    "REVIEW_QUEUE": KafkaTopic(
        name="agency.ontology.review-queue",
        partitions=3,
        replication_factor=1,
        retention_ms=30 * 24 * 3600 * 1000,  # 30 days
        cleanup_policy="delete",
        description="Low-confidence or conflicting extractions → human review. Partition key: document_id.",
    ),
    # ── Stage 6: Elasticsearch index sync ───────────────────────────────────
    "INDEX_UPDATE": KafkaTopic(
        name="agency.ontology.index-update",
        partitions=6,
        replication_factor=1,
        retention_ms=3 * 24 * 3600 * 1000,   # 3 days
        cleanup_policy="delete",
        description="Elasticsearch index sync events. Partition key: connector_id.",
    ),
    # ── Dead letter queue ────────────────────────────────────────────────────
    "DLQ": KafkaTopic(
        name="agency.ontology.dlq",
        partitions=3,
        replication_factor=1,
        retention_ms=90 * 24 * 3600 * 1000,  # 90 days
        cleanup_policy="delete",
        description="Failed messages after max retries. Partition key: original_topic:original_partition.",
    ),
    # ── Agent feedback ───────────────────────────────────────────────────────
    "FEEDBACK": KafkaTopic(
        name="agency.ontology.feedback",
        partitions=3,
        replication_factor=1,
        retention_ms=30 * 24 * 3600 * 1000,  # 30 days
        cleanup_policy="delete",
        description="Agent quality feedback on concept lookups. Partition key: concept_id.",
    ),
}


# Consumer group names per stage — consistent across all workers
CONSUMER_GROUPS = {
    "SOURCE_SCAN":    "agency-ontology-source-scan-cg",
    "EXTRACT":        "agency-ontology-extract-cg",
    "LLM_EXTRACT":    "agency-ontology-llm-extract-cg",
    "NORMALIZE":      "agency-ontology-normalize-cg",
    "COMMIT":         "agency-ontology-commit-cg",
    "REVIEW_QUEUE":   "agency-ontology-review-cg",
    "INDEX_UPDATE":   "agency-ontology-index-update-cg",
    "FEEDBACK":       "agency-ontology-feedback-cg",
}
