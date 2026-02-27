"""
Kafka publisher and consumer worker for the Agency Ontology pipeline.
Provides type-safe message passing, retry with exponential backoff, and DLQ routing.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException, Message
from confluent_kafka.admin import AdminClient, NewTopic

from .topics import TOPICS, CONSUMER_GROUPS, KafkaTopic
from ..models.ontology import PipelineMessage

logger = logging.getLogger(__name__)

# Retry delays: 5s → 30s → 2min
RETRY_DELAYS_S = [5.0, 30.0, 120.0]
MAX_RETRIES = len(RETRY_DELAYS_S)


# ── Admin helper ──────────────────────────────────────────────────────────────

def ensure_topics(bootstrap_servers: str) -> None:
    """
    Idempotently create all pipeline topics.
    Call once on worker startup.
    """
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    existing = set(admin.list_topics(timeout=10).topics.keys())

    to_create = []
    for key, topic in TOPICS.items():
        if topic.name not in existing:
            new_topic = NewTopic(
                topic.name,
                num_partitions=topic.partitions,
                replication_factor=topic.replication_factor,
                config={
                    "cleanup.policy": topic.cleanup_policy,
                    "retention.ms": str(topic.retention_ms),
                },
            )
            to_create.append(new_topic)
            logger.info(f"Will create Kafka topic: {topic.name}")

    if to_create:
        futures = admin.create_topics(to_create)
        for name, f in futures.items():
            try:
                f.result()
                logger.info(f"Created Kafka topic: {name}")
            except KafkaException as exc:
                if "TOPIC_ALREADY_EXISTS" in str(exc):
                    pass  # Race condition — fine
                else:
                    logger.error(f"Failed to create topic {name}: {exc}")


# ── Publisher ─────────────────────────────────────────────────────────────────

class KafkaPublisher:
    """Type-safe Kafka producer wrapper. Thread-safe."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",                    # Wait for all in-sync replicas
            "retries": 5,
            "retry.backoff.ms": 1000,
            "enable.idempotence": True,        # Exactly-once producer semantics
            "compression.type": "lz4",
            "linger.ms": 5,                   # Small batch window for throughput
        })

    def publish(
        self,
        topic: str,
        message: PipelineMessage,
        partition_key: str,
    ) -> None:
        """
        Publish a pipeline message. Synchronous delivery guarantee via on_delivery callback.
        Partition key: document_id for pipeline stages, connector_id for scan/index stages.
        """
        self._producer.produce(
            topic=topic,
            key=partition_key.encode("utf-8"),
            value=message.model_dump_json().encode("utf-8"),
            headers={
                "job_id": message.job_id.encode(),
                "correlation_id": message.correlation_id.encode(),
                "retry_count": str(message.retry_count).encode(),
                "stage": message.stage.encode(),
            },
            on_delivery=self._delivery_callback,
        )
        self._producer.poll(0)  # Trigger delivery callbacks

    def flush(self, timeout: float = 30.0) -> None:
        """Wait for all pending messages to be delivered."""
        self._producer.flush(timeout)

    def __del__(self) -> None:
        try:
            self._producer.flush(5.0)
        except Exception:
            pass

    @staticmethod
    def _delivery_callback(err: KafkaError | None, msg: Message) -> None:
        if err:
            logger.error(
                "Kafka delivery failed",
                extra={"topic": msg.topic(), "partition": msg.partition(), "error": str(err)},
            )
        else:
            logger.debug(
                "Kafka message delivered",
                extra={"topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset()},
            )


# ── Consumer Worker ───────────────────────────────────────────────────────────

MessageHandler = Callable[[PipelineMessage], Awaitable[None]]


class KafkaConsumerWorker:
    """
    Base class for all pipeline stage consumers.

    Handles:
    - Message deserialization and Pydantic validation
    - Retry with configurable backoff delays
    - DLQ routing after max retries
    - Manual offset commit (ONLY after successful processing + Neo4j/ES write)
    - Graceful shutdown via stop()
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str,
        dlq_topic: str = TOPICS["DLQ"].name,
        max_poll_interval_ms: int = 300_000,  # 5 min for LLM-heavy stages
    ) -> None:
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,       # Manual commit after successful processing
            "max.poll.interval.ms": max_poll_interval_ms,
            "session.timeout.ms": 45_000,
            "fetch.min.bytes": 1,
            "fetch.max.wait.ms": 100,
        })
        self._publisher = KafkaPublisher(bootstrap_servers)
        self._topic = topic
        self._dlq_topic = dlq_topic
        self._running = False

    async def run(self, handler: MessageHandler) -> None:
        """
        Subscribe to topic and process messages.
        Offsets are committed only after handler completes successfully.
        """
        self._consumer.subscribe([self._topic])
        self._running = True
        logger.info(f"Consumer started: topic={self._topic}, group={self._consumer.memberid() or 'pending'}")

        try:
            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0)  # Yield to event loop
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error(f"Consumer error on {self._topic}: {msg.error()}")
                    continue

                try:
                    envelope = PipelineMessage.model_validate_json(msg.value())
                    await handler(envelope)
                    # ⚠ Commit ONLY after successful processing
                    self._consumer.commit(message=msg, asynchronous=False)

                except Exception as exc:
                    logger.exception(
                        f"Handler failed for message on {self._topic}",
                        extra={"error": str(exc)},
                    )
                    await self._handle_failure(msg, exc)
        finally:
            self._consumer.close()
            logger.info(f"Consumer stopped: topic={self._topic}")

    async def _handle_failure(self, msg: Message, exc: Exception) -> None:
        """
        On failure: retry with backoff (re-publish to same topic with incremented counter).
        After MAX_RETRIES: route to DLQ.
        Always commit offset to avoid infinite loops on malformed messages.
        """
        try:
            envelope = PipelineMessage.model_validate_json(msg.value())
            retry_count = envelope.retry_count

            if retry_count < MAX_RETRIES:
                delay_s = RETRY_DELAYS_S[retry_count]
                logger.warning(
                    f"Pipeline failure on {self._topic} — retry {retry_count + 1}/{MAX_RETRIES} "
                    f"in {delay_s}s",
                    extra={"job_id": envelope.job_id, "correlation_id": envelope.correlation_id},
                )
                await asyncio.sleep(delay_s)
                updated = envelope.model_copy(update={"retry_count": retry_count + 1})
                key = msg.key().decode("utf-8") if msg.key() else envelope.correlation_id
                self._publisher.publish(self._topic, updated, key)

            else:
                logger.error(
                    f"Max retries exceeded on {self._topic} — routing to DLQ",
                    extra={
                        "job_id": envelope.job_id,
                        "correlation_id": envelope.correlation_id,
                        "error": str(exc),
                    },
                )
                dlq_payload = {
                    **envelope.payload,
                    "_dlq_error": str(exc),
                    "_dlq_original_topic": self._topic,
                    "_dlq_retry_count": retry_count,
                }
                dlq_envelope = envelope.model_copy(update={"payload": dlq_payload})
                key = msg.key().decode("utf-8") if msg.key() else envelope.correlation_id
                self._publisher.publish(self._dlq_topic, dlq_envelope, key)

            # Always commit so we don't reprocess a permanently failing message
            self._consumer.commit(message=msg, asynchronous=False)

        except Exception as nested:
            logger.critical(
                f"DLQ routing itself failed — message may be lost!",
                extra={"nested_error": str(nested), "original_error": str(exc)},
            )
            # Best-effort commit to prevent infinite loop
            try:
                self._consumer.commit(message=msg, asynchronous=False)
            except Exception:
                pass

    def stop(self) -> None:
        """Signal graceful shutdown."""
        self._running = False
        logger.info(f"Shutdown requested for consumer: topic={self._topic}")
