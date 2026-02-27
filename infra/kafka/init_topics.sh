#!/bin/bash
# infra/kafka/init_topics.sh
# Creates all Kafka topics for the Agency Ontology pipeline on first run.
# Run after Kafka broker is healthy.

set -e

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}"
KAFKA_BIN="${KAFKA_BIN:-/opt/kafka/bin}"

echo "Creating Agency Ontology Kafka topics on $BOOTSTRAP_SERVER ..."

create_topic() {
  local name="$1"
  local partitions="$2"
  local replication="$3"
  local retention_ms="$4"  # -1 = infinite
  local cleanup_policy="$5"

  echo "  → Creating topic: $name (partitions=$partitions, replication=$replication, retention=$retention_ms ms)"

  $KAFKA_BIN/kafka-topics.sh \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$name" \
    --partitions "$partitions" \
    --replication-factor "$replication" \
    --config "cleanup.policy=$cleanup_policy" \
    --config "retention.ms=$retention_ms"

  echo "    ✓ $name"
}

# ── Stage 1: Source scanning ──────────────────────────────────────────────────
# Partition key: connector_id
create_topic "agency.ontology.source-scan" 3 1 -1 "delete"

# ── Stage 2: Per-document extraction ──────────────────────────────────────────
# Partition key: document_id (guarantees ordered processing per document)
# Infinite retention — replay capability — DO NOT CHANGE
create_topic "agency.ontology.extract" 12 1 -1 "delete"

# ── Stage 3: LLM extraction (rate-limited by LLM capacity) ───────────────────
# Partition key: document_id
# Infinite retention — replay capability — DO NOT CHANGE
create_topic "agency.ontology.llm-extract" 6 1 -1 "delete"

# ── Stage 4: Normalization and entity resolution ──────────────────────────────
# Partition key: document_id
create_topic "agency.ontology.normalize" 12 1 604800000 "delete"  # 7 days

# ── Stage 5a: Ready to commit to graph ───────────────────────────────────────
# Partition key: document_id
create_topic "agency.ontology.commit" 6 1 604800000 "delete"  # 7 days

# ── Stage 5b: Flagged for human review ───────────────────────────────────────
# Partition key: document_id
create_topic "agency.ontology.review-queue" 3 1 2592000000 "delete"  # 30 days

# ── Stage 6: Index updates (Elasticsearch sync) ───────────────────────────────
# Partition key: connector_id
create_topic "agency.ontology.index-update" 6 1 259200000 "delete"  # 3 days

# ── Dead letter queue ─────────────────────────────────────────────────────────
# Partition key: original_topic + original_partition
create_topic "agency.ontology.dlq" 3 1 7776000000 "delete"  # 90 days

# ── Feedback from agents ──────────────────────────────────────────────────────
# Partition key: concept_id
create_topic "agency.ontology.feedback" 3 1 2592000000 "delete"  # 30 days

echo ""
echo "✓ All Agency Ontology Kafka topics created successfully."
echo ""

# Verify
echo "Listing all agency.ontology.* topics:"
$KAFKA_BIN/kafka-topics.sh \
  --bootstrap-server "$BOOTSTRAP_SERVER" \
  --list | grep "agency.ontology" || echo "  (none found — check bootstrap server)"
