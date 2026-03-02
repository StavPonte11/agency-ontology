"""
hierarchy_cache.py — Ancestor path materialization for hierarchy-aware retrieval.

After a concept's INSTANCE_OF / SUBCLASS_OF / PART_OF_HIERARCHY edges are committed
to Neo4j, call `recompute_ancestor_cache` to:

1. Walk upward through the hierarchy (up to 10 hops)
2. Upsert rows into the `concept_ancestor_cache` Postgres table
3. Return ancestor info for the caller to update Elasticsearch

Trigger: INDEX_UPDATE Kafka topic, or called inline from GraphIngestor after
hierarchical concept ingestion.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Cypher queries ─────────────────────────────────────────────────────────────

ANCESTOR_CYPHER = """
MATCH path = (c:Concept {id: $conceptId})
  -[:INSTANCE_OF|SUBCLASS_OF|PART_OF_HIERARCHY*1..10]->(ancestor:Concept)
RETURN ancestor.id       AS ancestorId,
       ancestor.name     AS ancestorName,
       length(path)      AS depth,
       [r IN relationships(path) | type(r)] AS relationPath
ORDER BY depth ASC
"""

FIND_DIRECT_PARENTS_CYPHER = """
MATCH (c:Concept {id: $conceptId})-[r:INSTANCE_OF|SUBCLASS_OF]->(parent:Concept)
RETURN parent.id AS parentId, parent.name AS parentName, type(r) AS relationType
LIMIT 1
"""


async def recompute_ancestor_cache(
    concept_id: str,
    neo4j_driver: Any,
    pg_conn: Any,
) -> list[dict]:
    """
    Materialise the full ancestor chain for a concept into Postgres.

    Parameters
    ----------
    concept_id:
        The Neo4j concept ID (UUID string).
    neo4j_driver:
        An async Neo4j driver (neo4j.AsyncDriver).
    pg_conn:
        An asyncpg connection or any compatible async PostgreSQL connection.

    Returns
    -------
    List of ancestor dicts: [{ancestorId, ancestorName, depth, relationPath}]
    """
    logger.info(f"Recomputing ancestor cache for concept_id={concept_id}")

    # 1. Fetch ancestors from Neo4j
    async with neo4j_driver.session() as session:
        result = await session.run(ANCESTOR_CYPHER, conceptId=concept_id)
        records = await result.data()

    if not records:
        logger.debug(f"No ancestors found for concept_id={concept_id}")
        return []

    logger.info(f"Found {len(records)} ancestor(s) for concept_id={concept_id}")

    # 2. Upsert into Postgres concept_ancestor_cache
    upsert_sql = """
        INSERT INTO concept_ancestor_cache
            (concept_id, ancestor_id, depth, relation_path, computed_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (concept_id, ancestor_id)
        DO UPDATE SET
            depth         = EXCLUDED.depth,
            relation_path = EXCLUDED.relation_path,
            computed_at   = NOW()
    """
    for rec in records:
        relation_path = ">".join(rec["relationPath"])
        try:
            await pg_conn.execute(
                upsert_sql,
                concept_id,
                rec["ancestorId"],
                rec["depth"],
                relation_path,
            )
        except Exception as exc:
            logger.warning(
                f"Ancestor cache upsert failed for "
                f"concept={concept_id} ancestor={rec['ancestorId']}: {exc}"
            )

    return records


def build_es_hierarchy_update(
    concept_id: str,
    ancestors: list[dict],
    direct_instance_of: str | None = None,
    direct_subclass_of: str | None = None,
) -> dict:
    """
    Build the Elasticsearch partial update payload for hierarchy fields.

    Use the result of `recompute_ancestor_cache` to populate ancestor_ids,
    ancestor_names, and hierarchy_depth in the ES concept document.
    """
    ancestor_ids = [a["ancestorId"] for a in ancestors]
    ancestor_names = [a["ancestorName"] for a in ancestors]
    depth = max((a["depth"] for a in ancestors), default=0)

    return {
        "doc": {
            "ancestor_ids":    ancestor_ids,
            "ancestor_names":  ancestor_names,
            "hierarchy_depth": depth,
            "instance_of":     direct_instance_of,
            "subclass_of":     direct_subclass_of,
        }
    }
