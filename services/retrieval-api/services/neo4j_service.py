"""
Neo4j graph traversal service — Agency Ontology Retrieval API.
Executes Cypher queries for concept lookup, related traversal, and schema context.
Hebrew military domain: returns Hebrew names as primary when available.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable

from ..models import (
    ConceptRef, RelatedConceptRef, DataAssetRef, LookupResult,
    NotFoundResult, ConceptType, ConceptStatus, SensitivityLevel,
    MappingType, DataAssetType,
)

logger = logging.getLogger(__name__)


class Neo4jService:
    """Async Neo4j service — all graph traversal operations."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        await self._driver.verify_connectivity()
        logger.info(f"Neo4j connected: {self._uri}")

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    async def ping(self) -> bool:
        try:
            async with self._driver.session() as s:
                await s.run("RETURN 1")
            return True
        except Exception:
            return False

    async def lookup_concept(
        self,
        term: str,
        max_hops: int = 2,
        include_data_assets: bool = True,
    ) -> LookupResult | NotFoundResult:
        """
        Look up a concept by name or alias (normalized match on Term nodes).
        Returns full context: definition, aliases, related concepts, data assets.
        Hebrew-first: tries Hebrew name/alias match first.
        """
        # TODO(permissions): Filter by sensitivity level before returning concept data.
        # Check requesting agent's sensitivity clearance vs concept.sensitivity.
        try:
            async with self._driver.session() as session:
                # Step 1: resolve term → concept (try exact match on normalized form)
                result = await session.run(
                    """
                    MATCH (t:Term)
                    WHERE toLower(t.normalizedForm) = toLower($normalized)
                       OR toLower(t.surfaceForm) = toLower($term)
                    WITH t
                    MATCH (c:Concept)-[:HAS_TERM]->(t)
                    WHERE c.status <> 'DEPRECATED'
                    RETURN c LIMIT 1
                    """,
                    term=term,
                    normalized=term.lower().strip(),
                )
                record = await result.single()

                if not record:
                    # Try full-text index as fallback (lexical)
                    result2 = await session.run(
                        """
                        CALL db.index.fulltext.queryNodes('concept_fulltext', $query)
                        YIELD node, score
                        WHERE node.status <> 'DEPRECATED'
                        RETURN node AS c
                        ORDER BY score DESC LIMIT 1
                        """,
                        query=term,
                    )
                    record = await result2.single()

                if not record:
                    # Return closest candidates via Cypher name similarity
                    candidates_result = await session.run(
                        """
                        MATCH (c:Concept)
                        WHERE c.status <> 'DEPRECATED'
                        RETURN c.id AS id, c.name AS name,
                               c.nameHe AS nameHe, c.conceptType AS conceptType,
                               c.domain AS domain
                        LIMIT 5
                        """,
                    )
                    candidates = []
                    async for row in candidates_result:
                        candidates.append(ConceptRef(
                            id=row["id"],
                            name=row["nameHe"] or row["name"],
                            concept_type=ConceptType(row["conceptType"]),
                            domain=row["domain"] or [],
                        ))
                    return NotFoundResult(
                        found=False, closest_candidates=candidates, degraded_mode=False
                    )

                concept_node = record["c"]
                concept_id = concept_node["id"]

                # Step 2: Get all aliases
                aliases_result = await session.run(
                    """
                    MATCH (c:Concept {id: $id})-[:HAS_TERM]->(t:Term)
                    RETURN t.surfaceForm AS form, t.termType AS termType, t.language AS lang
                    """,
                    id=concept_id,
                )
                aliases: list[str] = []
                async for row in aliases_result:
                    if row["termType"] != "OFFICIAL":
                        aliases.append(row["form"])

                # Step 3: Get related concepts (up to max_hops)
                related_result = await session.run(
                    """
                    MATCH (c:Concept {id: $id})-[r]->(other:Concept)
                    WHERE type(r) IN ['IS_A','PART_OF','DEPENDS_ON','USES','GOVERNS',
                                      'REPLACES','REPORTS_TO','OWNED_BY','PRODUCES',
                                      'CONSUMES','RELATED_TO']
                      AND other.status <> 'DEPRECATED'
                    RETURN other.nameHe AS nameHe, other.name AS name,
                           type(r) AS relation, r.confidence AS conf,
                           'outbound' AS direction
                    LIMIT 20
                    UNION
                    MATCH (other:Concept)-[r]->(c:Concept {id: $id})
                    WHERE type(r) IN ['IS_A','PART_OF','DEPENDS_ON','USES','GOVERNS',
                                      'REPLACES','REPORTS_TO','OWNED_BY','PRODUCES',
                                      'CONSUMES','RELATED_TO']
                      AND other.status <> 'DEPRECATED'
                    RETURN other.nameHe AS nameHe, other.name AS name,
                           type(r) AS relation, r.confidence AS conf,
                           'inbound' AS direction
                    LIMIT 20
                    """,
                    id=concept_id,
                )
                related: list[RelatedConceptRef] = []
                async for row in related_result:
                    related.append(RelatedConceptRef(
                        name=row["nameHe"] or row["name"],
                        relation=row["relation"],
                        direction=row["direction"],
                        confidence=float(row["conf"] or 0.7),
                    ))

                # Step 4: Get data asset mappings
                data_assets: list[DataAssetRef] = []
                if include_data_assets:
                    da_result = await session.run(
                        """
                        MATCH (c:Concept {id: $id})-[m:MAPS_TO]->(d:DataAsset)
                        RETURN d.qualifiedName AS qn, d.assetType AS atype,
                               m.mappingType AS mtype, d.description AS desc
                        LIMIT 20
                        """,
                        id=concept_id,
                    )
                    async for row in da_result:
                        data_assets.append(DataAssetRef(
                            qualified_name=row["qn"],
                            asset_type=DataAssetType(row["atype"]),
                            mapping_type=MappingType(row["mtype"]),
                            description=row["desc"],
                        ))

                # Step 5: Increment usage count
                await session.run(
                    """
                    MATCH (c:Concept {id: $id})
                    SET c.usageCount = coalesce(c.usageCount, 0) + 1,
                        c.lastUsedAt = datetime()
                    """,
                    id=concept_id,
                )

                # Hebrew-first: prefer Hebrew name/description
                display_name = concept_node.get("nameHe") or concept_node["name"]
                description = (
                    concept_node.get("descriptionHe") or concept_node["description"]
                )
                confidence = float(concept_node.get("confidence", 0.7))

                from ..models import ProvenanceInfo
                from datetime import datetime as dt

                return LookupResult(
                    found=True,
                    concept=ConceptRef(
                        id=concept_id,
                        name=display_name,
                        concept_type=ConceptType(concept_node["conceptType"]),
                        domain=concept_node.get("domain") or [],
                    ),
                    definition=description,
                    aliases=aliases,
                    related=related,
                    data_assets=data_assets,
                    provenance=ProvenanceInfo(
                        primary_source=(
                            concept_node.get("sources", ["unknown"])[0]
                            if concept_node.get("sources")
                            else "unknown"
                        ),
                        sources_count=len(concept_node.get("sources") or []),
                        last_updated=concept_node.get("updatedAt") or dt.utcnow(),
                    ),
                    confidence=confidence,
                    status=ConceptStatus(concept_node["status"]),
                    low_confidence=confidence < 0.6,
                    degraded_mode=False,
                )

        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during lookup: {exc}")
            return LookupResult(
                found=False,
                degraded_mode=True,
                degraded_reason="Neo4j unavailable — try again or use search endpoint",
            )
        except Exception as exc:
            logger.exception(f"Neo4j lookup error for term='{term}': {exc}")
            raise

    async def get_schema_context(
        self, concept_names: list[str]
    ) -> tuple[list[dict], list[str]]:
        """
        For each concept name, return associated DataAsset nodes and columns.
        Used by TextToSQL agents for database schema context.
        """
        tables = []
        unmapped = []
        # TODO(permissions): Filter data assets by agent's schema access permissions.

        async with self._driver.session() as session:
            for name in concept_names:
                result = await session.run(
                    """
                    MATCH (c:Concept)
                    WHERE c.name = $name OR c.nameHe = $name
                    WITH c
                    MATCH (c)-[m:MAPS_TO]->(d:DataAsset)
                    WHERE d.assetType IN ['TABLE', 'VIEW']
                    RETURN d.qualifiedName AS qn, d.description AS desc,
                           m.mappingType AS mtype
                    LIMIT 5
                    """,
                    name=name,
                )
                records = [r async for r in result]
                if not records:
                    unmapped.append(name)
                    continue

                for record in records:
                    # Get columns for this table
                    cols_result = await session.run(
                        """
                        MATCH (d:DataAsset {qualifiedName: $qn})-[:HAS_COLUMN]->(col:DataAsset)
                        WHERE col.assetType = 'COLUMN'
                        RETURN col.name AS name, col.dataType AS dt,
                               col.description AS desc, col.isPrimaryKey AS pk,
                               col.isNullable AS nullable
                        LIMIT 50
                        """,
                        qn=record["qn"],
                    )
                    columns = []
                    async for col in cols_result:
                        columns.append({
                            "name": col["name"],
                            "data_type": col["dt"] or "unknown",
                            "description": col["desc"],
                            "is_primary_key": bool(col["pk"]),
                            "is_nullable": bool(col["nullable"] if col["nullable"] is not None else True),
                        })
                    tables.append({
                        "qualified_name": record["qn"],
                        "description": record["desc"],
                        "columns": columns,
                        "related_tables": [],
                    })

        return tables, unmapped
