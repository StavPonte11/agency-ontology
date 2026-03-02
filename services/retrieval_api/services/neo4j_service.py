"""
Neo4j graph traversal service — Agency Ontology Retrieval API.
Executes Cypher queries for concept lookup, related traversal, and schema context.
Hebrew military domain: returns Hebrew names as primary when available.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.pipeline.models.ontology import (
    ConceptRef,
    ConceptStatus,
    ConceptType,
    DataAssetRef,
    DataAssetType,
    LookupResult,
    MappingType,
    NotFoundResult,
    ProvenanceInfo,
    RelatedConceptRef,
)

from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable

# from ..models import (
#     ConceptRef, RelatedConceptRef, DataAssetRef, LookupResult,
#     NotFoundResult, ConceptType, ConceptStatus, SensitivityLevel,
#     MappingType, DataAssetType,
# )

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

    # ── Hierarchy traversal methods ───────────────────────────────────────────

    async def get_ancestors(self, concept_id: str) -> list[dict]:
        """
        Walk upward through the hierarchy (up to 10 hops).
        Returns list of {concept_id, concept_name, depth, relation} dicts, nearest-first.
        """
        query = """
        MATCH path = (c:Concept {id: $conceptId})
          -[:INSTANCE_OF|SUBCLASS_OF|PART_OF_HIERARCHY*1..10]->(ancestor:Concept)
        RETURN ancestor.id       AS concept_id,
               ancestor.name     AS concept_name,
               length(path)      AS depth,
               [r IN relationships(path) | type(r)][length(path)-1] AS relation
        ORDER BY depth ASC
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, conceptId=concept_id)
                return [dict(record) for record in await result.data()]
        except Exception as exc:
            logger.warning(f"get_ancestors failed for {concept_id}: {exc}")
            return []

    async def get_children(self, concept_id: str) -> dict[str, list[dict]]:
        """
        Get direct subclasses and instances of a concept (one hop down).
        Returns {"subclasses": [...], "instances": [...]} each with {id, name, conceptType, domain}.
        """
        query = """
        MATCH (child:Concept)-[r:INSTANCE_OF|SUBCLASS_OF]->(c:Concept {id: $conceptId})
        RETURN child.id          AS id,
               child.name        AS name,
               child.conceptType AS concept_type,
               child.domain      AS domain,
               type(r)           AS relation_type
        ORDER BY child.name ASC
        LIMIT 50
        """
        subclasses, instances = [], []
        try:
            async with self._driver.session() as session:
                result = await session.run(query, conceptId=concept_id)
                async for record in result:
                    entry = {"id": record["id"], "name": record["name"],
                             "concept_type": record["concept_type"],
                             "domain": record["domain"] or []}
                    if record["relation_type"] == "SUBCLASS_OF":
                        subclasses.append(entry)
                    else:
                        instances.append(entry)
        except Exception as exc:
            logger.warning(f"get_children failed for {concept_id}: {exc}")
        return {"subclasses": subclasses, "instances": instances}

    async def get_siblings(self, concept_id: str) -> list[dict]:
        """
        Get sibling concepts: share a common parent class, not the concept itself.
        Returns list of {id, name, shared_parent} dicts.
        """
        query = """
        MATCH (c:Concept {id: $conceptId})-[:INSTANCE_OF|SUBCLASS_OF]->(parent:Concept)
        MATCH (sibling:Concept)-[:INSTANCE_OF|SUBCLASS_OF]->(parent)
        WHERE sibling.id <> $conceptId
        RETURN sibling.id   AS id,
               sibling.name AS name,
               parent.name  AS shared_parent
        LIMIT 20
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, conceptId=concept_id)
                return [dict(record) for record in await result.data()]
        except Exception as exc:
            logger.warning(f"get_siblings failed for {concept_id}: {exc}")
            return []

    async def get_concept_description(self, concept_id: str) -> Optional[dict]:
        """Lightweight fetch of name + description for inherited context assembly."""
        query = """
        MATCH (c:Concept {id: $conceptId})
        RETURN c.name AS name, c.description AS description
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, conceptId=concept_id)
                record = await result.single()
                return dict(record) if record else None
        except Exception as exc:
            logger.warning(f"get_concept_description failed for {concept_id}: {exc}")
            return None

    async def find_concept_by_name(self, name: str) -> Optional[str]:
        """Case-insensitive exact name lookup. Returns concept_id or None."""
        query = """
        MATCH (c:Concept)
        WHERE toLower(c.name) = toLower($name)
        RETURN c.id AS concept_id LIMIT 1
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, name=name)
                record = await result.single()
                return record["concept_id"] if record else None
        except Exception as exc:
            logger.warning(f"find_concept_by_name failed for {name!r}: {exc}")
            return None

    async def get_multilingual_labels(self, concept_id: str) -> list[dict]:
        """Fetch all Label nodes attached to a concept."""
        query = """
        MATCH (c:Concept {id: $conceptId})-[:HAS_LABEL]->(l:Label)
        RETURN l.language AS language, l.label AS label,
               l.description AS description, l.aliases AS aliases
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, conceptId=concept_id)
                return [dict(record) for record in await result.data()]
        except Exception as exc:
            logger.warning(f"get_multilingual_labels failed for {concept_id}: {exc}")
            return []

    async def get_statements(self, concept_id: str) -> list[dict]:
        """Fetch all Statement nodes attached to a concept."""
        query = """
        MATCH (c:Concept {id: $conceptId})-[:HAS_STATEMENT]->(s:Statement)
        RETURN s.propertyId AS property_id, s.propertyLabel AS property_label,
               s.valueType AS value_type, s.value AS value, s.confidence AS confidence
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(query, conceptId=concept_id)
                return [dict(record) for record in await result.data()]
        except Exception as exc:
            logger.warning(f"get_statements failed for {concept_id}: {exc}")
            return []

    async def assemble_inherited_context(
        self,
        concept_id: str,
        ancestor_path: list[dict],
        token_budget: int = 500,
    ) -> Optional[str]:
        """
        Walk the ancestor path and collect descriptions from each ancestor class.
        Assemble into a compact inherited context string for LLM consumption.
        Stops when token_budget is exhausted.

        Result format:
        "Inherited context:
        • As a [Territorial Brigade]: Regional military formation responsible for...
        • As a [Brigade]: Combined arms military unit..."
        """
        if not ancestor_path:
            return None

        lines: list[str] = ["Inherited context:"]
        tokens_used = 0

        for step in ancestor_path:
            ancestor = await self.get_concept_description(step["concept_id"])
            if not ancestor or not ancestor.get("description"):
                continue
            line = f"• As a [{step['concept_name']}]: {ancestor['description']}"
            line_tokens = len(line.split())
            if tokens_used + line_tokens > token_budget:
                break
            lines.append(line)
            tokens_used += line_tokens

        return "\n".join(lines) if len(lines) > 1 else None
