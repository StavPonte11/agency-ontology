"""
Graph Ingestor — Agency Ontology Pipeline
Writes extracted concepts, terms, relationships, and data mappings to Neo4j.
Uses MERGE semantics (idempotent upserts) so re-running the pipeline is safe.

Node/relationship schema matches exactly what neo4j_service.py (retrieval API) queries.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable

from ..models.ontology import (
    ConceptStatus,
    ExtractedConcept,
    ExtractedDataMapping,
    ExtractedRelationship,
    HierarchicalExtractionOutput,
    HierarchicalConcept,
    LLMExtractionOutput,
    SensitivityLevel,
)
from ..resolution.entity_resolver import normalize_term

logger = logging.getLogger(__name__)


# ── Cypher queries ────────────────────────────────────────────────────────────

_ENSURE_INDEXES_QUERIES = [
    # Uniqueness constraint on Concept.id
    "CREATE CONSTRAINT concept_id_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
    # Uniqueness constraint on Term.id
    "CREATE CONSTRAINT term_id_unique IF NOT EXISTS FOR (t:Term) REQUIRE t.id IS UNIQUE",
    # Uniqueness constraint on DataAsset.qualifiedName
    "CREATE CONSTRAINT data_asset_qn_unique IF NOT EXISTS FOR (d:DataAsset) REQUIRE d.qualifiedName IS UNIQUE",
    # Uniqueness constraint on Document.id
    "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (doc:Document) REQUIRE doc.id IS UNIQUE",
    # Lookup index on Concept.name (for resolver queries)
    "CREATE INDEX concept_name_idx IF NOT EXISTS FOR (c:Concept) ON (c.name)",
    # Lookup index on Concept.nameHe
    "CREATE INDEX concept_name_he_idx IF NOT EXISTS FOR (c:Concept) ON (c.nameHe)",
    # Lookup index on Term.surfaceForm (for retrieval API)
    "CREATE INDEX term_surface_form_idx IF NOT EXISTS FOR (t:Term) ON (t.surfaceForm)",
    # Lookup index on Term.normalizedForm
    "CREATE INDEX term_normalized_form_idx IF NOT EXISTS FOR (t:Term) ON (t.normalizedForm)",
]

# Full-text index (separate from schema constraints)
_FULLTEXT_INDEX_QUERY = """
CREATE FULLTEXT INDEX concept_fulltext IF NOT EXISTS
FOR (c:Concept)
ON EACH [c.name, c.nameHe, c.description, c.descriptionHe]
"""

# ── Hierarchical Cypher queries ──────────────────────────────────────────

_SET_CONCEPT_CLASS_FLAGS = """
MATCH (c:Concept {id: $concept_id})
SET c.isClass      = $is_class,
    c.isDeprecated = $is_deprecated,
    c.supersededBy = $superseded_by,
    c.updatedAt    = datetime()
"""

_MERGE_LABEL = """
MERGE (l:Label {conceptId: $concept_id, language: $language})
SET l.label       = $label,
    l.description = $description,
    l.aliases     = $aliases,
    l.updatedAt   = datetime()
WITH l
MATCH (c:Concept {id: $concept_id})
MERGE (c)-[:HAS_LABEL {language: $language}]->(l)
"""

_MERGE_STATEMENT = """
MERGE (s:Statement {conceptId: $concept_id, propertyId: $property_id})
SET s.propertyLabel = $property_label,
    s.valueType     = $value_type,
    s.value         = $value,
    s.confidence    = $confidence,
    s.updatedAt     = datetime()
WITH s
MATCH (c:Concept {id: $concept_id})
MERGE (c)-[:HAS_STATEMENT]->(s)
"""

_FIND_CONCEPT_BY_NAME = """
MATCH (c:Concept)
WHERE toLower(c.name) = toLower($name)
RETURN c.id AS concept_id
LIMIT 1
"""

_CREATE_CANDIDATE_CLASS = """
MERGE (c:Concept {name: $name})
ON CREATE SET
    c.id          = $id,
    c.description = $description,
    c.conceptType = 'TERM',
    c.domain      = ['General'],
    c.status      = 'CANDIDATE',
    c.sensitivity = 'INTERNAL',
    c.confidence  = 0.6,
    c.isClass     = true,
    c.sources     = [],
    c.usageCount  = 0,
    c.createdAt   = datetime(),
    c.updatedAt   = datetime()
RETURN c.id AS concept_id
"""

_MERGE_HIERARCHY_EDGE = """
MATCH (child:Concept {id: $child_id})
MATCH (parent:Concept {id: $parent_id})
CALL apoc.merge.relationship(
    child,
    $relation_type,
    {confidence: $confidence},
    {source: $source_quote, createdAt: datetime()},
    parent
) YIELD rel
RETURN rel
"""

# Fallback when APOC is unavailable — uses dynamic Cypher dispatch
_MERGE_HIERARCHY_INSTANCE_OF = """
MATCH (child:Concept {id: $child_id})
MATCH (parent:Concept {id: $parent_id})
MERGE (child)-[r:INSTANCE_OF {confidence: $confidence}]->(parent)
ON CREATE SET r.source = $source_quote, r.createdAt = datetime()
RETURN r
"""
_MERGE_HIERARCHY_SUBCLASS_OF = """
MATCH (child:Concept {id: $child_id})
MATCH (parent:Concept {id: $parent_id})
MERGE (child)-[r:SUBCLASS_OF {confidence: $confidence}]->(parent)
ON CREATE SET r.source = $source_quote, r.createdAt = datetime()
RETURN r
"""
_MERGE_HIERARCHY_PART_OF = """
MATCH (child:Concept {id: $child_id})
MATCH (parent:Concept {id: $parent_id})
MERGE (child)-[r:PART_OF_HIERARCHY {confidence: $confidence}]->(parent)
ON CREATE SET r.source = $source_quote, r.createdAt = datetime()
RETURN r
"""

_CYCLE_CHECK_CYPHER = """
RETURN EXISTS {
    MATCH (potential_ancestor:Concept {id: $parent_id})
    -[:INSTANCE_OF|SUBCLASS_OF|PART_OF_HIERARCHY*1..10]->(child:Concept {id: $child_id})
} AS would_create_cycle
"""

_HIERARCHY_CYPHER_MAP = {
    "INSTANCE_OF":       _MERGE_HIERARCHY_INSTANCE_OF,
    "SUBCLASS_OF":       _MERGE_HIERARCHY_SUBCLASS_OF,
    "PART_OF_HIERARCHY": _MERGE_HIERARCHY_PART_OF,
}


_MERGE_CONCEPT = """
MERGE (c:Concept {id: $id})
ON CREATE SET
    c.name               = $name,
    c.nameHe             = $name_he,
    c.description        = $description,
    c.descriptionHe      = $description_he,
    c.conceptType        = $concept_type,
    c.domain             = $domain,
    c.status             = $status,
    c.sensitivity        = $sensitivity,
    c.confidence         = $confidence,
    c.sources            = [$source],
    c.usageCount         = 0,
    c.createdAt          = datetime(),
    c.updatedAt          = datetime()
ON MATCH SET
    c.updatedAt          = datetime(),
    c.confidence         = CASE WHEN $confidence > c.confidence THEN $confidence ELSE c.confidence END,
    c.sources            = CASE
                             WHEN NOT $source IN c.sources
                             THEN c.sources + [$source]
                             ELSE c.sources
                           END
RETURN c.id AS concept_id
"""

_MERGE_TERM = """
MATCH (c:Concept {id: $concept_id})
MERGE (t:Term {normalizedForm: $normalized_form, language: $language})
ON CREATE SET
    t.id           = $term_id,
    t.surfaceForm  = $surface_form,
    t.normalizedForm = $normalized_form,
    t.termType     = $term_type,
    t.language     = $language,
    t.frequency    = 1,
    t.firstSeenAt  = datetime(),
    t.lastSeenAt   = datetime()
ON MATCH SET
    t.frequency    = coalesce(t.frequency, 0) + 1,
    t.lastSeenAt   = datetime()
MERGE (c)-[:HAS_TERM]->(t)
"""

_MERGE_RELATIONSHIP = """
MATCH (from_c:Concept {name: $from_name})
MATCH (to_c:Concept {name: $to_name})
MERGE (from_c)-[r:{rel_type}]->(to_c)
ON CREATE SET
    r.confidence  = $confidence,
    r.sourceQuote = $source_quote,
    r.createdAt   = datetime()
ON MATCH SET
    r.confidence  = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END
"""

_MERGE_RELATIONSHIP_BY_HE = """
MATCH (from_c:Concept)
WHERE from_c.name = $from_name OR from_c.nameHe = $from_name
MATCH (to_c:Concept)
WHERE to_c.name = $to_name OR to_c.nameHe = $to_name
WITH from_c, to_c
MERGE (from_c)-[r:{rel_type}]->(to_c)
ON CREATE SET
    r.confidence  = $confidence,
    r.sourceQuote = $source_quote,
    r.createdAt   = datetime()
ON MATCH SET
    r.confidence  = CASE WHEN $confidence > r.confidence THEN $confidence ELSE r.confidence END
"""

_MERGE_DATA_ASSET = """
MERGE (d:DataAsset {qualifiedName: $qualified_name})
ON CREATE SET
    d.id          = $asset_id,
    d.name        = $name,
    d.assetType   = $asset_type,
    d.createdAt   = datetime(),
    d.updatedAt   = datetime()
ON MATCH SET
    d.updatedAt   = datetime()
WITH d
MATCH (c:Concept)
WHERE c.name = $concept_name OR c.nameHe = $concept_name
WITH c, d
MERGE (c)-[m:MAPS_TO {qualifiedName: $qualified_name}]->(d)
ON CREATE SET
    m.mappingType = $mapping_type,
    m.confidence  = $confidence,
    m.notes       = $notes,
    m.createdAt   = datetime()
"""

_MERGE_DOCUMENT = """
MERGE (doc:Document {id: $doc_id})
ON CREATE SET
    doc.title       = $title,
    doc.chunkId     = $chunk_id,
    doc.connectorId = $connector_id,
    doc.createdAt   = datetime()
ON MATCH SET
    doc.updatedAt   = datetime()
RETURN doc.id AS doc_id
"""

_LINK_CONCEPT_TO_DOCUMENT = """
MATCH (c:Concept {id: $concept_id})
MATCH (doc:Document {id: $doc_id})
MERGE (c)-[:SOURCED_FROM]->(doc)
"""

# ── Impact domain: Site / Facility / Component node Cypher ────────────────────

_MERGE_SITE = """
MERGE (s:Site {name: $name})
ON CREATE SET
    s.nodeType      = 'SITE',
    s.category      = $category,
    s.sourceFile    = $source_file,
    s.createdAt     = datetime()
ON MATCH SET
    s.updatedAt     = datetime()
RETURN s.name AS site_name
"""

_MERGE_FACILITY = """
MERGE (f:Facility {name: $name, siteName: $site_name})
ON CREATE SET
    f.nodeType                    = 'FACILITY',
    f.siteName                    = $site_name,
    f.category                    = $category,
    f.responsibleBody             = $responsible_body,
    f.system                      = $system,
    f.supportAttackEffort         = $support_attack,
    f.supportDefenceControlEffort = $support_defence,
    f.supportIntelligenceEffort   = $support_intel,
    f.supportAlertEffort          = $support_alert,
    f.supportNationalEffort       = $support_national,
    f.defenceWithIronDome         = $defence_iron_dome,
    f.levelForDefenceUpperLayer   = $defence_upper_layer,
    f.hardening                   = $hardening,
    f.concealment                 = $concealment,
    f.distribution                = $distribution,
    f.recoveryCapability          = $recovery_capability,
    f.redundancy                  = $redundancy,
    f.mobility                    = $mobility,
    f.polygon                     = $polygon,
    f.centralPoint                = $central_point,
    f.refinedCoordinate           = $refined_coordinate,
    f.operationalSignificance     = $operational_significance,
    f.mitigation_procedures        = $mitigation_procedures,
    f.sourceFile                  = $source_file,
    f.createdAt                   = datetime()
ON MATCH SET
    f.updatedAt               = datetime(),
    f.responsibleBody         = CASE WHEN $responsible_body <> '' THEN $responsible_body ELSE f.responsibleBody END,
    f.defenceWithIronDome     = CASE WHEN $defence_iron_dome <> '' THEN $defence_iron_dome ELSE f.defenceWithIronDome END,
    f.operationalSignificance = CASE WHEN $operational_significance IS NOT NULL THEN $operational_significance ELSE f.operationalSignificance END,
    f.mitigation_procedures    = CASE WHEN $mitigation_procedures IS NOT NULL THEN $mitigation_procedures ELSE f.mitigation_procedures END
RETURN f.name AS facility_name
"""

_MERGE_COMPONENT = """
MERGE (c:Component {name: $name, facilityName: $facility_name, siteName: $site_name})
ON CREATE SET
    c.nodeType      = 'COMPONENT',
    c.facilityName  = $facility_name,
    c.siteName      = $site_name,
    c.category      = $category,
    c.system        = $system,
    c.sourceFile    = $source_file,
    c.createdAt     = datetime()
ON MATCH SET
    c.updatedAt     = datetime()
RETURN c.name AS component_name
"""

# Generic node MERGEs for reference targets
_MERGE_GENERIC_NODE = """
MERGE (n:{label} {{name: $name}})
ON CREATE SET n.nodeType = $node_type, n.createdAt = datetime()
ON MATCH SET n.updatedAt = datetime()
RETURN n.name AS name
"""

# Site -> Facility containment
_MERGE_SITE_CONTAINS_FACILITY = """
MATCH (s:Site {name: $site_name})
MATCH (f:Facility {name: $facility_name, siteName: $site_name})
MERGE (s)-[r:CONTAINS]->(f)
ON CREATE SET r.createdAt = datetime()
"""

# Facility -> Component containment
_MERGE_FACILITY_CONTAINS_COMPONENT = """
MATCH (f:Facility {name: $facility_name, siteName: $site_name})
MATCH (c:Component {name: $component_name, facilityName: $facility_name})
MERGE (f)-[r:CONTAINS]->(c)
ON CREATE SET r.createdAt = datetime()
"""

# Generic typed impact edge between any two named nodes
# Edge type is injected as a string — we validate it against a safe allowlist
_ALLOWED_EDGE_TYPES = {
    "BACKUP_FOR", "RELATED_TO", "POWERED_BY", "FUELED_BY",
    "OPERATED_BY", "PART_OF_SYSTEM", "PROTECTED_BY", "AERIAL_DEFENSE_ZONE",
    "AFFECTS", "USES", "FEEDS", "CONTAINS", "HOSTS"
}

_MERGE_IMPACT_EDGE_BETWEEN_NAMES = """
MERGE (from_n {{name: $from_name}})
ON CREATE SET from_n.nodeType = $from_type, from_n.createdAt = datetime()
MERGE (to_n {{name: $to_name}})
ON CREATE SET to_n.nodeType = $to_type, to_n.createdAt = datetime()
"""

# ── Ingestor class ─────────────────────────────────────────────────────────────


class GraphIngestor:
    """
    Writes LLM extraction output to Neo4j using MERGE (idempotent upserts).

    All schema matches what neo4j_service.py (retrieval API) already queries:
    - (:Concept)-[:HAS_TERM]->(:Term)
    - (:Concept)-[RELATION_TYPE]->(:Concept)
    - (:Concept)-[:MAPS_TO]->(:DataAsset)
    - (:Concept)-[:SOURCED_FROM]->(:Document)
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    @classmethod
    async def create(cls, uri: str, user: str, password: str) -> "GraphIngestor":
        """Create a GraphIngestor with its own driver (for standalone use)."""
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        await driver.verify_connectivity()
        instance = cls(driver)
        await instance.ensure_indexes()
        return instance

    async def close(self) -> None:
        """Close the driver if owned by this ingestor."""
        if self._driver:
            await self._driver.close()

    async def ensure_indexes(self) -> None:
        """
        Create uniqueness constraints and indexes required for MERGE operations.
        Idempotent — safe to call on every startup.
        """
        async with self._driver.session() as session:
            for query in _ENSURE_INDEXES_QUERIES:
                try:
                    await session.run(query)
                except Exception as exc:
                    # Non-fatal: index may already exist with a different name
                    logger.debug(f"Index creation skipped (may already exist): {exc}")
            try:
                await session.run(_FULLTEXT_INDEX_QUERY)
            except Exception as exc:
                logger.debug(f"Fulltext index creation skipped: {exc}")
        logger.info("Neo4j indexes and constraints are active.")

    async def ingest_impact_row(
        self,
        row_content: dict[str, Any],
        source_file: str,
        llm_extraction: Optional[Any] = None,
    ) -> dict[str, int]:
        """
        Ingest a single row from an Excel impact dataset into Neo4j.
        Creates Site -> Facility -> Component hierarchy.
        Creates structured edges based on column roles.
        Creates LLM-extracted free-text edges.
        """
        stats = {"nodes": 0, "edges": 0}

        site_name = row_content.get("site_name")
        facility_name = row_content.get("facility_name")
        component_name = row_content.get("component_name")
        structured_refs = row_content.get("structured_refs", {})
        categoricals = row_content.get("categoricals", {})
        
        if not site_name or not facility_name:
            # Should have been caught by ReviewQueue, zero-op gracefully here
            return stats

        async with self._driver.session() as session:
            # 1. Merge Site (Location)
            res = await session.run("""
                MERGE (s:Site {name: $site_name})
                ON CREATE SET s.id = randomUUID(), s.createdAt = datetime()
                RETURN s.id AS id
            """, site_name=site_name)
            if (await res.single()):
                stats["nodes"] += 1

            # 2. Merge Facility
            res = await session.run("""
                MERGE (f:Facility {name: $facility_name, site_name: $site_name})
                ON CREATE SET 
                    f.id = randomUUID(), 
                    f.createdAt = datetime(),
                    f.source_file = $source_file
                SET f.category = $category
                RETURN f.id AS id
            """, 
            facility_name=facility_name, 
            site_name=site_name,
            source_file=source_file,
            category=categoricals.get("category", "") or "Unknown")
            if (await res.single()):
                stats["nodes"] += 1

            # 3. Link Site -> Facility (CONTAINS)
            res = await session.run("""
                MATCH (s:Site {name: $site}), (f:Facility {name: $fac, site_name: $site})
                MERGE (s)-[r:CONTAINS]->(f)
                RETURN r
            """, site=site_name, fac=facility_name)
            if (await res.single()):
                stats["edges"] += 1

            # 4. Optional Component
            if component_name:
                res = await session.run("""
                    MERGE (c:Component {name: $comp, facility_name: $fac})
                    ON CREATE SET c.id = randomUUID(), c.createdAt = datetime()
                    RETURN c.id AS id
                """, comp=component_name, fac=facility_name)
                if (await res.single()):
                    stats["nodes"] += 1
                
                res = await session.run("""
                    MATCH (f:Facility {name: $fac, site_name: $site}), (c:Component {name: $comp, facility_name: $fac})
                    MERGE (f)-[r:CONTAINS]->(c)
                    RETURN r
                """, fac=facility_name, site=site_name, comp=component_name)
                if (await res.single()):
                    stats["edges"] += 1

            # Determine the 'leaf' node that acts as the source for all outbound edges
            # Usually the Component if it exists, otherwise the Facility.
            source_node_type = "Component" if component_name else "Facility"
            source_node_name = component_name if component_name else facility_name
            fac_constraint = f", facility_name: '{facility_name}'" if component_name else f", site_name: '{site_name}'"

            # 5. Process Structured Refs
            edge_mapping = {
                "primary_backup": "BACKUP_FOR",
                "secondary_primary": "BACKUP_FOR", # Typo in dataset headers
                "related_facilty": "RELATED_TO",
                "connected_power_station": "POWERED_BY",
                "connection_to_strategic_fuel_reserves": "FUELED_BY",
                "responsible_body": "OPERATED_BY",
                "system": "PART_OF_SYSTEM",
                "site_by_aerial_defense": "AERIAL_DEFENSE_ZONE"
            }
            
            for col_name, target_value in structured_refs.items():
                if not target_value:
                    continue
                edge_type = edge_mapping.get(col_name.lower().strip(), "DEPENDS_ON")
                
                # Treat structured targets generally as Facilities for simplicity (unless specific like Operator/System)
                target_label = "Facility"
                if edge_type == "OPERATED_BY": target_label = "Department"
                elif edge_type == "PART_OF_SYSTEM": target_label = "System"
                
                res = await session.run(f"""
                    MERGE (t:{target_label} {{name: $target}})
                    ON CREATE SET t.id = randomUUID(), t.createdAt = datetime()
                    WITH t
                    MATCH (src:{source_node_type} {{name: $src_name {fac_constraint} }})
                    MERGE (src)-[r:{edge_type}]->(t)
                    RETURN r
                """, target=target_value, src_name=source_node_name)
                if (await res.single()):
                    stats["edges"] += 1

            # 6. Process LLM Extracted Free-Text Edges
            if llm_extraction and getattr(llm_extraction, "edges", None):
                for edge in llm_extraction.edges:
                    clean_type = str(edge.edge_type).replace(" ", "_").upper()
                    # Ensure basic labels
                    from_label = str(edge.from_type).capitalize() if edge.from_type else "Facility"
                    to_label = str(edge.to_type).capitalize() if edge.to_type else "Facility"
                    
                    if from_label not in ["Site", "Facility", "Component", "System", "Department"]:
                        from_label = "Facility"
                    if to_label not in ["Site", "Facility", "Component", "System", "Department"]:
                        to_label = "Facility"

                    try:
                        res = await session.run(f"""
                            MERGE (from_n:{from_label} {{name: $from_name}})
                            ON CREATE SET from_n.id = randomUUID(), from_n.createdAt = datetime()
                            WITH from_n
                            MERGE (to_n:{to_label} {{name: $to_name}})
                            ON CREATE SET to_n.id = randomUUID(), to_n.createdAt = datetime()
                            WITH from_n, to_n
                            MERGE (from_n)-[r:{clean_type}]->(to_n)
                            ON CREATE SET 
                                r.criticality = $crit,
                                r.source_column = $src_col,
                                r.createdAt = datetime()
                            RETURN r
                        """, 
                        from_name=edge.from_entity,
                        to_name=edge.to_entity,
                        crit=edge.criticality or "MEDIUM",
                        src_col=edge.source_column or "LLM_Extracted")
                        
                        if (await res.single()):
                            stats["edges"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to ingest LLM edge {edge.from_entity}-[{clean_type}]->{edge.to_entity}: {e}")

        return stats

    async def ingest(
        self,
        extraction: LLMExtractionOutput,
        document_id: str,
        source_title: str,
        chunk_id: str,
        connector_id: str = "manual",
    ) -> dict[str, int]:
        """
        Write all extracted concepts, terms, relationships, and data_mappings to Neo4j.

        Returns a summary dict: {concepts, terms, relationships, data_mappings, errors}
        """
        stats = {
            "concepts": 0,
            "terms": 0,
            "relationships": 0,
            "data_mappings": 0,
            "errors": 0,
        }

        try:
            async with self._driver.session() as session:
                # 1. Upsert the Document node for provenance
                doc_node_id = f"{document_id}::{chunk_id}"
                await session.run(
                    _MERGE_DOCUMENT,
                    doc_id=doc_node_id,
                    title=source_title,
                    chunk_id=chunk_id,
                    connector_id=connector_id,
                )

                # 2. Upsert each concept + its terms (+ hierarchical extras if applicable)
                concept_id_map: dict[str, str] = {}  # name → neo4j concept_id
                is_hierarchical = isinstance(extraction, HierarchicalExtractionOutput)
                stats.update({"labels": 0, "statements": 0, "hierarchy_edges": 0})

                for concept in extraction.concepts:
                    concept_id = await self._ingest_concept(
                        session, concept, source_title, doc_node_id
                    )
                    if concept_id:
                        concept_id_map[concept.name] = concept_id
                        if hasattr(concept, "name_he") and concept.name_he:
                            concept_id_map[concept.name_he] = concept_id
                        stats["concepts"] += 1
                        stats["terms"] += len(getattr(concept, "terms", []))

                        # Hierarchical extras (labels, statements, hierarchy edges)
                        if is_hierarchical:
                            from ..models.ontology import HierarchicalConcept as HC
                            if isinstance(concept, HC):
                                h_stats = await self._ingest_hierarchical_concept(
                                    session, concept, concept_id
                                )
                                stats["labels"]          += h_stats.get("labels", 0)
                                stats["statements"]      += h_stats.get("statements", 0)
                                stats["hierarchy_edges"] += h_stats.get("hierarchy_edges", 0)

                # 3. Upsert relationships between concepts
                for rel in extraction.relationships:
                    ok = await self._ingest_relationship(session, rel)
                    if ok:
                        stats["relationships"] += 1
                    else:
                        stats["errors"] += 1

                for mapping in extraction.data_mappings:
                    ok = await self._ingest_data_mapping(session, mapping)
                    if ok:
                        stats["data_mappings"] += 1
                    else:
                        stats["errors"] += 1

            logger.info(
                f"Ingested {stats['concepts']} concepts, {stats['terms']} terms, "
                f"{stats['relationships']} rels into Neo4j for chunk={chunk_id}"
            )
        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during ingestion: {exc}")
            stats["errors"] += 1
        except Exception as exc:
            logger.error(f"Graph ingestion failed for chunk={chunk_id}: {exc}")
            stats["errors"] += 1

        return stats

    async def _ingest_concept(
        self,
        session,
        concept: ExtractedConcept,
        source_title: str,
        doc_node_id: str,
    ) -> Optional[str]:
        """MERGE a Concept node and all its Term nodes. Returns the concept id."""
        try:
            # Deterministic ID: normalize name to avoid dupe concepts named differently
            concept_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, normalize_term(concept.name)))

            # Determine sensitivity: military codenames default to CONFIDENTIAL
            from ..models.ontology import ConceptType
            sensitivity = SensitivityLevel.CONFIDENTIAL
            if concept.concept_type in (ConceptType.ROLE, ConceptType.TERM):
                sensitivity = SensitivityLevel.INTERNAL

            result = await session.run(
                _MERGE_CONCEPT,
                id=concept_id,
                name=concept.name,
                name_he=concept.name_he,
                description=concept.description,
                description_he=concept.description_he,
                concept_type=concept.concept_type.value if hasattr(concept.concept_type, "value") else str(concept.concept_type),
                domain=concept.domain,
                status=ConceptStatus.CANDIDATE.value,
                sensitivity=sensitivity.value,
                confidence=concept.confidence,
                source=source_title,
            )
            record = await result.single()
            if not record:
                return None

            # MERGE Term nodes
            for term in concept.terms:
                normalized = normalize_term(term.surface_form)
                term_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{normalized}::{term.language}"))
                try:
                    await session.run(
                        _MERGE_TERM,
                        concept_id=concept_id,
                        term_id=term_id,
                        surface_form=term.surface_form,
                        normalized_form=normalized,
                        term_type=term.term_type.value if hasattr(term.term_type, "value") else str(term.term_type),
                        language=term.language.value if hasattr(term.language, "value") else str(term.language),
                    )
                except Exception as exc:
                    logger.warning(f"Term merge failed for '{term.surface_form}' ({concept_id}): {exc}")

            # Link concept to source document
            try:
                await session.run(
                    _LINK_CONCEPT_TO_DOCUMENT,
                    concept_id=concept_id,
                    doc_id=doc_node_id,
                )
            except Exception as exc:
                logger.warning(f"Concept-document link failed for {concept_id}: {exc}")

            return concept_id

        except Exception as exc:
            logger.warning(
                f"Concept ingestion failed for '{concept.name}': {exc}"
            )
            return None

    async def _ingest_relationship(
        self,
        session,
        rel: ExtractedRelationship,
    ) -> bool:
        """MERGE a typed relationship between two Concept nodes."""
        try:
            rel_type = rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type)
            # Cypher relationship type cannot be parameterized — inject safely (enum values are ASCII)
            cypher = _MERGE_RELATIONSHIP_BY_HE.replace("{rel_type}", rel_type)
            await session.run(
                cypher,
                from_name=rel.from_concept_name,
                to_name=rel.to_concept_name,
                confidence=rel.confidence,
                source_quote=rel.source_quote[:500] if rel.source_quote else "",
            )
            return True
        except Exception as exc:
            logger.warning(
                f"Relationship merge failed: {rel.from_concept_name} -[{rel.relation_type}]-> {rel.to_concept_name}: {exc}"
            )
            return False

    async def _ingest_data_mapping(
        self,
        session,
        mapping: ExtractedDataMapping,
    ) -> bool:
        """MERGE a DataAsset node and link it to its Concept via MAPS_TO."""
        try:
            qualified_name = mapping.data_asset_qualified_name
            name_parts = qualified_name.split(".")
            asset_name = name_parts[-1] if name_parts else qualified_name
            asset_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, qualified_name))

            await session.run(
                _MERGE_DATA_ASSET,
                asset_id=asset_id,
                qualified_name=qualified_name,
                name=asset_name,
                asset_type="TABLE",   # Default — catalog connector sets real type
                concept_name=mapping.concept_name,
                mapping_type=mapping.mapping_type.value if hasattr(mapping.mapping_type, "value") else str(mapping.mapping_type),
                confidence=mapping.confidence,
                notes=mapping.notes,
            )
            return True
        except Exception as exc:
            logger.warning(
                f"Data mapping merge failed for '{mapping.concept_name}' → '{mapping.data_asset_qualified_name}': {exc}"
            )
            return False

    # ── Hierarchical ingestion helpers ────────────────────────────────────────

    async def _ingest_labels(
        self,
        session,
        concept_id: str,
        concept: HierarchicalConcept,
    ) -> int:
        """Upsert Label nodes (one per language) and HAS_LABEL edges. Returns count."""
        count = 0
        for lbl in concept.multilingual_labels:
            try:
                await session.run(
                    _MERGE_LABEL,
                    concept_id=concept_id,
                    language=lbl.language,
                    label=lbl.label,
                    description=lbl.description or "",
                    aliases=lbl.aliases,
                )
                count += 1
                logger.debug(f"Label upserted: {concept.name!r} [{lbl.language}] '{lbl.label}'")
            except Exception as exc:
                logger.warning(f"Label merge failed for {concept.name!r} [{lbl.language}]: {exc}")
        return count

    async def _ingest_statements(
        self,
        session,
        concept_id: str,
        concept: HierarchicalConcept,
    ) -> int:
        """Upsert Statement nodes and HAS_STATEMENT edges. Returns count."""
        count = 0
        for stmt in concept.statements:
            # Determine the stored value string
            if stmt.value_type == "concept_ref":
                value = stmt.concept_ref_id or ""
            elif stmt.value_type == "multilingual":
                value = str(stmt.multilingual_values) if stmt.multilingual_values else ""
            else:
                value = stmt.string_value or ""
            try:
                await session.run(
                    _MERGE_STATEMENT,
                    concept_id=concept_id,
                    property_id=stmt.property_id,
                    property_label=stmt.property_label,
                    value_type=stmt.value_type,
                    value=value,
                    confidence=stmt.confidence,
                )
                count += 1
                logger.debug(f"Statement upserted: {concept.name!r} {stmt.property_id}={value!r}")
            except Exception as exc:
                logger.warning(f"Statement merge failed for {concept.name!r} {stmt.property_id}: {exc}")
        return count

    async def _ingest_hierarchy(
        self,
        session,
        concept_id: str,
        concept: HierarchicalConcept,
    ) -> int:
        """
        Create INSTANCE_OF / SUBCLASS_OF / PART_OF_HIERARCHY edges.

        For each HierarchyRelation:
        1. Look up the target concept by name.
        2. If not found: auto-create a CANDIDATE class node and flag for review.
        3. Perform cycle check — skip edge if it would create a cycle.
        4. Upsert the typed hierarchy edge.

        Returns count of edges created.
        """
        count = 0
        for h in concept.hierarchy:
            relation = h.relation.upper().replace(" ", "_")
            if relation not in _HIERARCHY_CYPHER_MAP:
                logger.warning(f"Unknown hierarchy relation type {h.relation!r} for {concept.name!r}, skipping")
                continue

            # 1. Find target concept by name
            find_result = await session.run(_FIND_CONCEPT_BY_NAME, name=h.target_concept_name)
            find_record = await find_result.single()
            parent_id: str | None = find_record["concept_id"] if find_record else None

            # 2. Auto-create CANDIDATE class node if not found
            if not parent_id:
                auto_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"class::{h.target_concept_name.lower().strip()}"))
                logger.info(
                    f"Auto-creating CANDIDATE class '{h.target_concept_name}' "
                    f"(triggered by '{concept.name}', relation={relation})"
                )
                try:
                    create_result = await session.run(
                        _CREATE_CANDIDATE_CLASS,
                        name=h.target_concept_name,
                        id=auto_id,
                        description=f"Auto-created class node. Triggered by: {concept.name}. Awaiting human review.",
                    )
                    create_record = await create_result.single()
                    parent_id = create_record["concept_id"] if create_record else auto_id
                except Exception as exc:
                    logger.warning(f"Auto-class creation failed for '{h.target_concept_name}': {exc}")
                    continue

            # 3. Cycle check — skip edge if it would create a cycle
            try:
                cycle_result = await session.run(
                    _CYCLE_CHECK_CYPHER,
                    parent_id=parent_id,
                    child_id=concept_id,
                )
                cycle_record = await cycle_result.single()
                if cycle_record and cycle_record["would_create_cycle"]:
                    logger.warning(
                        f"Cycle detected: skipping {relation} from {concept.name!r} → {h.target_concept_name!r}"
                    )
                    continue
            except Exception as exc:
                logger.debug(f"Cycle check failed (non-fatal): {exc}")

            # 4. Create the typed hierarchy edge
            try:
                cypher = _HIERARCHY_CYPHER_MAP[relation]
                await session.run(
                    cypher,
                    child_id=concept_id,
                    parent_id=parent_id,
                    confidence=h.confidence,
                    source_quote=(h.source_quote or "")[:500],
                )
                count += 1
                logger.info(
                    f"Hierarchy edge: ({concept.name!r})-[:{relation}]->({h.target_concept_name!r})"
                )
            except Exception as exc:
                logger.warning(
                    f"Hierarchy edge failed {concept.name!r} -[{relation}]-> {h.target_concept_name!r}: {exc}"
                )

        return count

    async def _ingest_hierarchical_concept(
        self,
        session,
        concept: HierarchicalConcept,
        concept_id: str,
    ) -> dict[str, int]:
        """
        After the base concept is ingested, write the hierarchical extensions:
        multilingual labels, statements, class flags, and hierarchy edges.
        """
        stats: dict[str, int] = {"labels": 0, "statements": 0, "hierarchy_edges": 0}

        # Set is_class / is_deprecated flags on Concept node
        try:
            await session.run(
                _SET_CONCEPT_CLASS_FLAGS,
                concept_id=concept_id,
                is_class=concept.is_class,
                is_deprecated=concept.is_deprecated,
                superseded_by=concept.superseded_by or "",
            )
        except Exception as exc:
            logger.warning(f"Class flag set failed for {concept.name!r}: {exc}")

        stats["labels"]         = await self._ingest_labels(session, concept_id, concept)
        stats["statements"]     = await self._ingest_statements(session, concept_id, concept)
        stats["hierarchy_edges"] = await self._ingest_hierarchy(session, concept_id, concept)

        logger.debug(
            f"Hierarchical extras for {concept.name!r}: "
            f"{stats['labels']} labels, {stats['statements']} statements, "
            f"{stats['hierarchy_edges']} hierarchy edges"
        )
        return stats
