"""
Impact Analysis Service — Agency Ontology
==========================================
Core propagation engine implementing the Five-Layer Impact Stack.

Key design contracts (spec Part 10):
  1. Pre-operational status halt is encoded in Cypher WHERE clause — not post-filter.
     A PLANNED project's downstream clients are never reached.
  2. Propagation queries are bounded at database level via Cypher depth limit.
  3. Cycle safety is handled both by Neo4j path semantics and application-level visited set.
  4. is_single_point_of_failure and downstream_count are recomputed after every change.
  5. Historical incidents are immutable — agents can query but never write them.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable

from services.pipeline.models.ontology import (
    ClientTier,
    DependencyEdgeType,
    DisruptionType,
    HistoricalIncident,
    ImpactCriticality,
    ImpactedEntity,
    ImpactEntityType,
    ImpactHistoricalRequest,
    ImpactedEntity,
    MitigationOption,
    OperationalStatus,
    PropagationMode,
    PropagationResult,
    SituationReport,
)

logger = logging.getLogger(__name__)


# ── Impact-specific Neo4j index/constraint queries ────────────────────────────

_IMPACT_SCHEMA_QUERIES = [
    # HistoricalIncident node uniqueness
    "CREATE CONSTRAINT incident_id_unique IF NOT EXISTS FOR (i:HistoricalIncident) REQUIRE i.id IS UNIQUE",
    # Fast filter on operational status during propagation
    "CREATE INDEX concept_op_status IF NOT EXISTS FOR (c:Concept) ON (c.operationalStatus)",
    # Fast filter on impact entity type
    "CREATE INDEX concept_entity_type IF NOT EXISTS FOR (c:Concept) ON (c.entityType)",
    # Fast filter on criticality level
    "CREATE INDEX concept_criticality IF NOT EXISTS FOR (c:Concept) ON (c.criticalityLevel)",
    # Location lookup for incident retrieval
    "CREATE INDEX incident_location IF NOT EXISTS FOR (i:HistoricalIncident) ON (i.locationRefs)",
    # Pre-computed downstream count
    "CREATE INDEX concept_downstream_count IF NOT EXISTS FOR (c:Concept) ON (c.downstreamCount)",
]

# ── Propagation Cypher ────────────────────────────────────────────────────────

# Core traversal — pre-operational halt baked into WHERE
# The key invariant: if ANY intermediate node (after trigger) is PLANNED or SUSPENDED,
# the path stops there. Downstream nodes of pre-operational projects never appear.
_PROPAGATE_CYPHER = """
MATCH (trigger:Concept)
WHERE toLower(trigger.name) = toLower($entity_name)
   OR toLower(trigger.nameHe) = toLower($entity_name)
WITH trigger

// BFS traversal with depth guard
MATCH path = (trigger)
  -[:HOSTS|RUNS|OPERATES|SERVES|USES|FEEDS|STAFFED_BY*1..$max_depth]->(affected:Concept)
WHERE
  // PRE-OPERATIONAL HALT: path must not pass through a PLANNED/SUSPENDED project
  // after the trigger node. This halts the severity chain at pre-operational entities.
  ALL(n IN nodes(path)[1..]
    WHERE NOT (
        n.entityType = 'PROJECT'
        AND n.operationalStatus IN ['PLANNED', 'SUSPENDED']
        AND n <> affected   -- the terminated entity itself still appears (as MONITOR)
    )
  )
  AND affected <> trigger

WITH affected,
     length(path) AS hop_distance,
     [n IN nodes(path) | n.name] AS path_nodes,
     [r IN relationships(path) | {
        type: type(r),
        criticality: r.criticality,
        mitigationAvailable: r.mitigationAvailable,
        recoveryTimeHours: r.recoveryTimeHours,
        propagationMode: r.propagationMode
     }] AS path_edges,
     last(relationships(path)) AS last_rel,
     last(nodes(path)[..-1]) AS parent_node

// Deduplicate by affected node (keep shortest path)
WITH affected, min(hop_distance) AS hop_distance, path_nodes, path_edges, last_rel, parent_node
ORDER BY hop_distance ASC, affected.criticalityLevel ASC

RETURN
  affected.name AS name,
  affected.nameHe AS nameHe,
  coalesce(affected.entityType, 'UNKNOWN') AS entity_type,
  coalesce(affected.operationalStatus, 'ACTIVE') AS operational_status,
  coalesce(affected.criticalityLevel, 'MEDIUM') AS criticality_level,
  coalesce(affected.clientTier, null) AS client_tier,
  coalesce(affected.slaBreachHours, null) AS sla_breach_hours,
  coalesce(affected.isSinglePointOfFailure, false) AS is_spof,
  hop_distance,
  path_nodes,
  path_edges,
  coalesce(last_rel.criticality, 'MEDIUM') AS edge_criticality,
  coalesce(last_rel.mitigationAvailable, false) AS mitigation_available,
  coalesce(last_rel.recoveryTimeHours, null) AS recovery_time_hours,
  coalesce(last_rel.propagationMode, 'DIRECT') AS propagation_mode,
  type(last_rel) AS edge_type
LIMIT 500
"""

_REVERSE_QUERY_CYPHER = """
MATCH (target:Concept)
WHERE toLower(target.name) = toLower($entity_name)
   OR toLower(target.nameHe) = toLower($entity_name)
WITH target

MATCH path = (dependent:Concept)
  -[:HOSTS|RUNS|OPERATES|SERVES|USES|FEEDS|STAFFED_BY*1..$max_depth]->(target)
WHERE dependent <> target

WITH dependent,
     length(path) AS hop_distance,
     [n IN nodes(path) | n.name] AS path_nodes

WITH dependent, min(hop_distance) AS hop_distance, path_nodes
ORDER BY hop_distance ASC

RETURN
  dependent.name AS name,
  coalesce(dependent.entityType, 'UNKNOWN') AS entity_type,
  coalesce(dependent.operationalStatus, 'ACTIVE') AS operational_status,
  coalesce(dependent.criticalityLevel, 'MEDIUM') AS criticality_level,
  coalesce(dependent.downstreamCount, 0) AS downstream_count,
  hop_distance,
  path_nodes
LIMIT 200
"""

_COMPARE_LOCATIONS_CYPHER = """
MATCH (loc:Concept)
WHERE loc.entityType = 'LOCATION'
  AND toLower(loc.name) IN $location_names_lower

OPTIONAL MATCH (loc)
  -[:HOSTS|RUNS|OPERATES|SERVES|USES|FEEDS|STAFFED_BY*1..5]->(downstream:Concept)
WITH loc,
     count(DISTINCT downstream) AS total_downstream,
     count(DISTINCT CASE WHEN downstream.criticalityLevel = 'CRITICAL' AND downstream.entityType = 'PROJECT' THEN downstream END) AS critical_projects,
     count(DISTINCT CASE WHEN downstream.clientTier = 'TIER_1' THEN downstream END) AS tier1_clients,
     count(DISTINCT CASE WHEN downstream.isSinglePointOfFailure = true THEN downstream END) AS spof_entities

RETURN
  loc.name AS location_name,
  coalesce(loc.criticalityLevel, 'MEDIUM') AS criticality_level,
  coalesce(loc.downstreamCount, total_downstream) AS downstream_count,
  critical_projects,
  tier1_clients,
  spof_entities,
  total_downstream
ORDER BY total_downstream DESC
"""

_MITIGATIONS_CYPHER = """
MATCH (entity:Concept)
WHERE toLower(entity.name) = toLower($entity_name)
   OR toLower(entity.nameHe) = toLower($entity_name)
WITH entity

// Find BACKUP_FOR edges
OPTIONAL MATCH (backup:Concept)-[:BACKUP_FOR]->(entity)

// Find backup location reference
OPTIONAL MATCH (backupLoc:Concept {entityType: 'LOCATION'})
WHERE backupLoc.name = entity.backupLocationRef

// Find departments that can absorb this entity's function
OPTIONAL MATCH (altDept:Concept {entityType: 'DEPARTMENT'})
WHERE altDept.canOperateRemotely = true
  AND altDept.operationalStatus = 'ACTIVE'
  AND altDept.name <> entity.name

RETURN
  entity.name AS entity_name,
  entity.entityType AS entity_type,
  entity.hasBackup AS has_backup,
  entity.backupAssetRef AS backup_asset_ref,
  entity.backupLocationRef AS backup_location_ref,
  entity.hasFailover AS has_failover,
  entity.failoverTimeHours AS failover_time_hours,
  entity.canOperateRemotely AS can_operate_remotely,
  collect(DISTINCT backup.name) AS backup_entities,
  backupLoc.name AS backup_location_name,
  collect(DISTINCT altDept.name)[..3] AS alternative_departments
LIMIT 1
"""

_HISTORICAL_QUERY_CYPHER = """
MATCH (i:HistoricalIncident)
WHERE ANY(loc IN $location_names WHERE loc IN i.locationRefs)
   OR ANY(ent IN $entity_names WHERE ent IN i.entityRefs)
RETURN
  i.id AS id,
  i.incidentDate AS incident_date,
  i.title AS title,
  i.description AS description,
  i.locationRefs AS location_refs,
  i.entityRefs AS entity_refs,
  i.disruptionType AS disruption_type,
  i.actionsTaken AS actions_taken,
  i.outcome AS outcome,
  i.recoveryTimeHours AS recovery_time_hours,
  i.lessonsRecorded AS lessons_recorded,
  i.sourceDocument AS source_document,
  i.confidence AS confidence
ORDER BY i.incidentDate DESC
LIMIT 10
"""

# Ingest a HistoricalIncident node
_MERGE_INCIDENT = """
MERGE (i:HistoricalIncident {id: $id})
ON CREATE SET
  i.incidentDate    = $incident_date,
  i.title           = $title,
  i.description     = $description,
  i.locationRefs    = $location_refs,
  i.entityRefs      = $entity_refs,
  i.disruptionType  = $disruption_type,
  i.actionsTaken    = $actions_taken,
  i.outcome         = $outcome,
  i.recoveryTimeHours = $recovery_time_hours,
  i.lessonsRecorded = $lessons_recorded,
  i.sourceDocument  = $source_document,
  i.confidence      = $confidence,
  i.ingestedAt      = datetime()
ON MATCH SET
  i.confidence = CASE WHEN $confidence > i.confidence THEN $confidence ELSE i.confidence END
RETURN i.id AS incident_id
"""

# Link HistoricalIncident to Concept nodes (locations / entities)
_LINK_INCIDENT_TO_CONCEPT = """
MATCH (i:HistoricalIncident {id: $incident_id})
MATCH (c:Concept)
WHERE toLower(c.name) = toLower($concept_name)
   OR toLower(c.nameHe) = toLower($concept_name)
MERGE (i)-[:REFERENCES]->(c)
"""

# Set impact properties on an existing Concept node
_SET_IMPACT_PROPERTIES = """
MATCH (c:Concept)
WHERE toLower(c.name) = toLower($name) OR c.id = $concept_id
SET
  c.entityType           = $entity_type,
  c.operationalStatus    = $operational_status,
  c.criticalityLevel     = $criticality_level,
  c.clientTier           = $client_tier,
  c.slaBreachHours       = $sla_breach_hours,
  c.hasActiveSla         = $has_active_sla,
  c.backupLocationRef    = $backup_location_ref,
  c.canOperateRemotely   = $can_operate_remotely,
  c.hasBackup            = $has_backup,
  c.backupAssetRef       = $backup_asset_ref,
  c.hasFailover          = $has_failover,
  c.failoverTimeHours    = $failover_time_hours,
  c.isShared             = $is_shared,
  c.hasDesignatedBackup  = $has_designated_backup,
  c.updatedAt            = datetime()
RETURN c.id AS concept_id
"""

# Merge a typed dependency edge
_MERGE_DEPENDENCY_EDGE_TEMPLATE = """
MATCH (from_c:Concept)
WHERE toLower(from_c.name) = toLower($from_name)
   OR toLower(from_c.nameHe) = toLower($from_name)
MATCH (to_c:Concept)
WHERE toLower(to_c.name) = toLower($to_name)
   OR toLower(to_c.nameHe) = toLower($to_name)
MERGE (from_c)-[r:{edge_type}]->(to_c)
ON CREATE SET
  r.criticality        = $criticality,
  r.propagationMode    = $propagation_mode,
  r.mitigationAvailable = $mitigation_available,
  r.recoveryTimeHours  = $recovery_time_hours,
  r.condition          = $condition,
  r.createdAt          = datetime()
ON MATCH SET
  r.criticality        = $criticality,
  r.propagationMode    = $propagation_mode,
  r.mitigationAvailable = $mitigation_available,
  r.recoveryTimeHours  = $recovery_time_hours,
  r.updatedAt          = datetime()
RETURN type(r) AS rel_type
"""

# Background: recompute downstream counts for all Concept nodes
_RECOMPUTE_DOWNSTREAM_COUNTS = """
MATCH (c:Concept)
OPTIONAL MATCH (c)-[:HOSTS|RUNS|OPERATES|SERVES|USES|FEEDS|STAFFED_BY*1..10]->(downstream:Concept)
WITH c, count(DISTINCT downstream) AS cnt
SET c.downstreamCount = cnt,
    c.isSinglePointOfFailure = (
      cnt > 0
      AND coalesce(c.hasBackup, false) = false
      AND coalesce(c.hasFailover, false) = false
      AND coalesce(c.backupLocationRef, '') = ''
    )
"""


# ── Tier assignment logic ─────────────────────────────────────────────────────

def _assign_impact_tier(
    operational_status: str,
    criticality_level: str,
    mitigation_available: bool,
    edge_criticality: str,
    client_tier: Optional[str] = None,
    sla_breach_hours: Optional[int] = None,
) -> str:
    """
    Assign CRITICAL / HIGH / MONITOR tier to an impacted entity.

    Rules (derived from Part 1.4 canonical example + Part 5 spec):
    1. PLANNED or SUSPENDED operational status → always MONITOR (delay only, not harm)
    2. Edge criticality CRITICAL + no mitigation + ACTIVE → CRITICAL
    3. Edge criticality CRITICAL + mitigation available → HIGH
    4. Edge criticality HIGH + ACTIVE → HIGH
    5. TIER_1 client with SLA ≤ 24h → escalate to CRITICAL if no mitigation
    6. Everything else → MONITOR
    """
    # Rule 1: pre-operational always MONITOR
    if operational_status in ("PLANNED", "SUSPENDED"):
        return "MONITOR"

    # Rule 5: Tier-1 client with urgent SLA
    if client_tier == "TIER_1" and sla_breach_hours is not None and sla_breach_hours <= 24:
        return "CRITICAL" if not mitigation_available else "HIGH"

    # Rules 2-4
    if edge_criticality == "CRITICAL":
        return "HIGH" if mitigation_available else "CRITICAL"
    if edge_criticality == "HIGH":
        return "HIGH"

    return "MONITOR"


# ── Impact Service ─────────────────────────────────────────────────────────────

class ImpactService:
    """
    All impact-domain read and write operations against Neo4j.

    Methods:
      propagate_impact()      — core 5-layer traversal
      reverse_query()         — what depends on this entity?
      compare_locations()     — blast radius ranking
      find_mitigations()      — mitigation options for an entity
      get_historical_context() — past incidents linked to entities/locations
      ingest_incident()       — write HistoricalIncident (pipeline use only)
      ingest_dependency_edge() — write typed dep edge
      set_impact_properties() — write operational properties on Concept
      compute_graph_metrics() — background refresh of downstream_count
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    @classmethod
    async def create(cls, uri: str, user: str, password: str) -> "ImpactService":
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        await driver.verify_connectivity()
        instance = cls(driver)
        await instance.ensure_impact_schema()
        return instance

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    async def ensure_impact_schema(self) -> None:
        """Create Neo4j indexes and constraints for impact domain. Idempotent."""
        async with self._driver.session() as session:
            for query in _IMPACT_SCHEMA_QUERIES:
                try:
                    await session.run(query)
                except Exception as exc:
                    logger.debug(f"Impact schema query skipped (may exist): {exc}")
        logger.info("Impact schema indexes and constraints are active.")

    # ── Propagation ────────────────────────────────────────────────────────────

    async def propagate_impact(
        self,
        entity_name: str,
        disruption_type: DisruptionType = DisruptionType.UNKNOWN,
        max_depth: int = 5,
        include_mitigation: bool = True,
        include_historical: bool = True,
        is_simulation: bool = False,
    ) -> PropagationResult:
        """
        Traverse the dependency graph from trigger entity and produce a PropagationResult.

        Pre-operational halt is in the Cypher WHERE clause — PLANNED/SUSPENDED project
        nodes stop the path. Their downstream clients never appear in any tier.
        """
        try:
            async with self._driver.session() as session:
                # 1. Check trigger entity exists
                check = await session.run(
                    "MATCH (c:Concept) WHERE toLower(c.name) = toLower($n) OR toLower(c.nameHe) = toLower($n) RETURN c LIMIT 1",
                    n=entity_name,
                )
                record = await check.single()
                if not record:
                    return PropagationResult(
                        trigger_entity=entity_name,
                        trigger_entity_type=ImpactEntityType.LOCATION,
                        disruption_type=disruption_type,
                        is_simulation=is_simulation,
                        traversal_complete=True,
                        coverage_confidence=0.0,
                        low_coverage_entities=[entity_name],
                    )

                trigger_node = record["c"]
                trigger_entity_type = ImpactEntityType(
                    trigger_node.get("entityType", "LOCATION")
                ) if trigger_node.get("entityType") in ImpactEntityType._value2member_map_ else ImpactEntityType.LOCATION

                # 2. Run propagation
                result = await session.run(
                    _PROPAGATE_CYPHER,
                    entity_name=entity_name,
                    max_depth=max_depth,
                )

                critical_entities: list[ImpactedEntity] = []
                high_entities: list[ImpactedEntity] = []
                monitor_entities: list[ImpactedEntity] = []

                seen: set[str] = set()
                max_depth_seen = 0

                async for row in result:
                    name = row["name"] or row.get("nameHe", "")
                    if name in seen:
                        continue
                    seen.add(name)

                    op_status = row["operational_status"] or "ACTIVE"
                    crit_level = row["criticality_level"] or "MEDIUM"
                    edge_crit = row["edge_criticality"] or "MEDIUM"
                    mit_avail = bool(row["mitigation_available"])
                    client_tier_val = row.get("client_tier")
                    sla_hours = row.get("sla_breach_hours")
                    hop = int(row["hop_distance"])

                    tier = _assign_impact_tier(
                        operational_status=op_status,
                        criticality_level=crit_level,
                        mitigation_available=mit_avail,
                        edge_criticality=edge_crit,
                        client_tier=client_tier_val,
                        sla_breach_hours=sla_hours,
                    )

                    # Parse entity type safely
                    try:
                        etype = ImpactEntityType(row["entity_type"])
                    except ValueError:
                        etype = ImpactEntityType.LOCATION

                    # Parse propagation mode safely
                    try:
                        prop_mode = PropagationMode(row["propagation_mode"])
                    except ValueError:
                        prop_mode = PropagationMode.DIRECT

                    # Parse edge type safely
                    edge_type_val = row.get("edge_type")
                    try:
                        edge_type = DependencyEdgeType(edge_type_val) if edge_type_val else None
                    except ValueError:
                        edge_type = None

                    entity = ImpactedEntity(
                        name=name,
                        entity_type=etype,
                        operational_status=OperationalStatus(op_status) if op_status in OperationalStatus._value2member_map_ else OperationalStatus.ACTIVE,
                        criticality=ImpactCriticality(crit_level) if crit_level in ImpactCriticality._value2member_map_ else ImpactCriticality.MEDIUM,
                        hop_distance=hop,
                        propagation_path=list(row["path_nodes"] or []),
                        edge_type=edge_type,
                        propagation_mode=prop_mode,
                        mitigation_available=mit_avail,
                        recovery_time_hours=row.get("recovery_time_hours"),
                        impact_tier=tier,
                        client_tier=ClientTier(client_tier_val) if client_tier_val in ClientTier._value2member_map_ else None,
                        sla_breach_hours=sla_hours,
                        is_single_point_of_failure=bool(row.get("is_spof", False)),
                    )

                    if hop > max_depth_seen:
                        max_depth_seen = hop

                    if tier == "CRITICAL":
                        critical_entities.append(entity)
                    elif tier == "HIGH":
                        high_entities.append(entity)
                    else:
                        monitor_entities.append(entity)

        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during propagation: {exc}")
            return PropagationResult(
                trigger_entity=entity_name,
                trigger_entity_type=ImpactEntityType.LOCATION,
                disruption_type=disruption_type,
                is_simulation=is_simulation,
                traversal_complete=False,
                coverage_confidence=0.0,
                low_coverage_entities=[entity_name],
            )

        total = len(critical_entities) + len(high_entities) + len(monitor_entities)

        result_obj = PropagationResult(
            trigger_entity=entity_name,
            trigger_entity_type=trigger_entity_type,
            disruption_type=disruption_type,
            is_simulation=is_simulation,
            critical_entities=critical_entities,
            high_entities=high_entities,
            monitor_entities=monitor_entities,
            total_affected=total,
            max_depth_reached=max_depth_seen,
            traversal_complete=max_depth_seen < max_depth,
        )

        # Optionally fetch mitigations and historical context
        if include_mitigation and total > 0:
            all_critical_names = [e.name for e in critical_entities + high_entities]
            for name in all_critical_names[:5]:  # limit for performance
                mits = await self.find_mitigations(name)
                result_obj.mitigations.extend(mits)

        if include_historical:
            historical = await self.get_historical_context(
                entity_names=list(seen),
                location_names=[entity_name],
            )
            result_obj.historical_context = [h.model_dump() for h in historical]

        return result_obj

    # ── Reverse query ──────────────────────────────────────────────────────────

    async def reverse_query(
        self,
        entity_name: str,
        entity_type: Optional[ImpactEntityType] = None,
        max_depth: int = 3,
    ) -> dict[str, Any]:
        """Find all entities that depend on the queried entity (inbound dependency)."""
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    _REVERSE_QUERY_CYPHER,
                    entity_name=entity_name,
                    max_depth=max_depth,
                )
                dependents = []
                async for row in result:
                    dependents.append({
                        "name": row["name"],
                        "entity_type": row["entity_type"],
                        "operational_status": row["operational_status"],
                        "criticality_level": row["criticality_level"],
                        "downstream_count": row["downstream_count"],
                        "hop_distance": row["hop_distance"],
                        "path": list(row["path_nodes"] or []),
                    })

                is_spof = len(dependents) > 0 and len({
                    d["entity_type"] for d in dependents
                }) > 1

                return {
                    "entity_name": entity_name,
                    "dependent_entities": dependents,
                    "total_dependents": len(dependents),
                    "is_single_point_of_failure": is_spof,
                }
        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during reverse query: {exc}")
            return {"entity_name": entity_name, "dependent_entities": [], "error": str(exc)}

    # ── Location comparison ────────────────────────────────────────────────────

    async def compare_locations(
        self,
        location_names: list[str],
        metric: str = "downstream_count",
    ) -> list[dict[str, Any]]:
        """Compare blast radius of multiple locations. Returns ranked list."""
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    _COMPARE_LOCATIONS_CYPHER,
                    location_names_lower=[n.lower() for n in location_names],
                )
                rows = [dict(r) async for r in result]
                # Sort by requested metric
                rows.sort(key=lambda r: r.get(metric, 0), reverse=True)
                for i, row in enumerate(rows):
                    row["rank"] = i + 1
                return rows
        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during location compare: {exc}")
            return []

    # ── Mitigation finder ──────────────────────────────────────────────────────

    async def find_mitigations(
        self,
        entity_name: str,
        scenario_context: Optional[str] = None,
    ) -> list[MitigationOption]:
        """Retrieve all documented mitigation options for an entity."""
        options: list[MitigationOption] = []
        try:
            async with self._driver.session() as session:
                result = await session.run(_MITIGATIONS_CYPHER, entity_name=entity_name)
                record = await result.single()
                if not record:
                    return options

                # Backup entities (BACKUP_FOR edges)
                for backup_name in record["backup_entities"] or []:
                    if backup_name:
                        options.append(MitigationOption(
                            entity_name=entity_name,
                            option_type="redundant_asset",
                            description=f"Activate backup entity: {backup_name}",
                            source=backup_name,
                            confidence=0.95,
                        ))

                # Backup location ref
                if record.get("backup_location_name"):
                    options.append(MitigationOption(
                        entity_name=entity_name,
                        option_type="backup_location",
                        description=f"Relocate to backup location: {record['backup_location_name']}",
                        source=record["backup_location_name"],
                        confidence=0.9,
                    ))

                # Failover
                if record.get("has_failover"):
                    options.append(MitigationOption(
                        entity_name=entity_name,
                        option_type="documented_fallback",
                        description=f"Activate failover — estimated {record.get('failover_time_hours', '?')}h recovery",
                        source="documented_failover",
                        estimated_recovery_hours=record.get("failover_time_hours"),
                        confidence=0.9,
                    ))

                # Remote operation
                if record.get("can_operate_remotely"):
                    options.append(MitigationOption(
                        entity_name=entity_name,
                        option_type="documented_fallback",
                        description="Department can operate remotely — activate remote work protocol",
                        source="remote_capability",
                        confidence=0.85,
                    ))

                # Alternative departments
                for alt_dept in record.get("alternative_departments") or []:
                    if alt_dept:
                        options.append(MitigationOption(
                            entity_name=entity_name,
                            option_type="alternative_dept",
                            description=f"Redirect function to {alt_dept} (remote-capable)",
                            source=alt_dept,
                            confidence=0.7,
                        ))

                # Check historical incidents for precedent
                historical = await self.get_historical_context(
                    entity_names=[entity_name], location_names=[]
                )
                for incident in historical[:2]:
                    if incident.actions_taken:
                        options.append(MitigationOption(
                            entity_name=entity_name,
                            option_type="historical_precedent",
                            description=f"Historical precedent ({incident.incident_date or 'date unknown'}): {'; '.join(incident.actions_taken[:2])}",
                            source=incident.source_document,
                            estimated_recovery_hours=incident.recovery_time_hours,
                            confidence=incident.confidence,
                        ))

        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during mitigation query: {exc}")
        return options

    # ── Historical context ─────────────────────────────────────────────────────

    async def get_historical_context(
        self,
        entity_names: list[str],
        location_names: list[str],
        since_date: Optional[str] = None,
    ) -> list[HistoricalIncident]:
        """Retrieve historical incidents involving these entities/locations."""
        try:
            async with self._driver.session() as session:
                result = await session.run(
                    _HISTORICAL_QUERY_CYPHER,
                    entity_names=[n.lower() for n in entity_names],
                    location_names=[n.lower() for n in location_names],
                )
                incidents: list[HistoricalIncident] = []
                async for row in result:
                    dt_val = row.get("incident_date")
                    if since_date and dt_val:
                        try:
                            if str(dt_val) < since_date:
                                continue
                        except Exception:
                            pass
                    incidents.append(HistoricalIncident(
                        id=row["id"],
                        incident_date=str(row["incident_date"]) if row.get("incident_date") else None,
                        title=row["title"] or "",
                        description=row["description"] or "",
                        location_refs=list(row.get("location_refs") or []),
                        entity_refs=list(row.get("entity_refs") or []),
                        disruption_type=DisruptionType(row["disruption_type"]) if row.get("disruption_type") in DisruptionType._value2member_map_ else None,
                        actions_taken=list(row.get("actions_taken") or []),
                        outcome=row.get("outcome") or "",
                        recovery_time_hours=row.get("recovery_time_hours"),
                        lessons_recorded=list(row.get("lessons_recorded") or []),
                        source_document=row.get("source_document") or "",
                        confidence=float(row.get("confidence") or 0.8),
                    ))
                return incidents
        except ServiceUnavailable as exc:
            logger.error(f"Neo4j unavailable during historical query: {exc}")
            return []

    # ── Ingest operations (pipeline use only) ─────────────────────────────────

    async def ingest_incident(self, incident: HistoricalIncident) -> bool:
        """Write a HistoricalIncident node. Agents cannot call this — pipeline only."""
        try:
            async with self._driver.session() as session:
                await session.run(
                    _MERGE_INCIDENT,
                    id=incident.id,
                    incident_date=incident.incident_date,
                    title=incident.title,
                    description=incident.description,
                    location_refs=incident.location_refs,
                    entity_refs=incident.entity_refs,
                    disruption_type=incident.disruption_type.value if incident.disruption_type else None,
                    actions_taken=incident.actions_taken,
                    outcome=incident.outcome,
                    recovery_time_hours=incident.recovery_time_hours,
                    lessons_recorded=incident.lessons_recorded,
                    source_document=incident.source_document,
                    confidence=incident.confidence,
                )
                # Link to referenced concept nodes
                for concept_name in incident.location_refs + incident.entity_refs:
                    try:
                        await session.run(
                            _LINK_INCIDENT_TO_CONCEPT,
                            incident_id=incident.id,
                            concept_name=concept_name,
                        )
                    except Exception as exc:
                        logger.debug(f"Incident-concept link skipped for '{concept_name}': {exc}")
            return True
        except Exception as exc:
            logger.error(f"Failed to ingest incident '{incident.title}': {exc}")
            return False

    async def set_impact_properties(
        self,
        name: str,
        concept_id: str,
        props: dict[str, Any],
    ) -> bool:
        """Set operational impact properties on an existing Concept node."""
        try:
            async with self._driver.session() as session:
                await session.run(
                    _SET_IMPACT_PROPERTIES,
                    name=name,
                    concept_id=concept_id,
                    entity_type=props.get("entity_type", "LOCATION"),
                    operational_status=props.get("operational_status", "ACTIVE"),
                    criticality_level=props.get("criticality_level", "MEDIUM"),
                    client_tier=props.get("client_tier"),
                    sla_breach_hours=props.get("sla_breach_hours"),
                    has_active_sla=props.get("has_active_sla", False),
                    backup_location_ref=props.get("backup_location_ref"),
                    can_operate_remotely=props.get("can_operate_remotely", False),
                    has_backup=props.get("has_backup", False),
                    backup_asset_ref=props.get("backup_asset_ref"),
                    has_failover=props.get("has_failover", False),
                    failover_time_hours=props.get("failover_time_hours"),
                    is_shared=props.get("is_shared", False),
                    has_designated_backup=props.get("has_designated_backup", False),
                )
            return True
        except Exception as exc:
            logger.error(f"set_impact_properties failed for '{name}': {exc}")
            return False

    async def ingest_dependency_edge(
        self,
        from_name: str,
        to_name: str,
        edge_type: str,
        criticality: str = "MEDIUM",
        propagation_mode: str = "DIRECT",
        mitigation_available: bool = False,
        recovery_time_hours: Optional[int] = None,
        condition: Optional[str] = None,
    ) -> bool:
        """MERGE a typed dependency edge between two Concept nodes."""
        # Validate edge type against allowed types
        valid_types = {e.value for e in DependencyEdgeType}
        if edge_type not in valid_types:
            logger.warning(f"Invalid dependency edge type '{edge_type}' — skipping")
            return False

        cypher = _MERGE_DEPENDENCY_EDGE_TEMPLATE.replace("{edge_type}", edge_type)
        try:
            async with self._driver.session() as session:
                await session.run(
                    cypher,
                    from_name=from_name,
                    to_name=to_name,
                    criticality=criticality,
                    propagation_mode=propagation_mode,
                    mitigation_available=mitigation_available,
                    recovery_time_hours=recovery_time_hours,
                    condition=condition,
                )
            return True
        except Exception as exc:
            logger.error(f"Dependency edge failed: {from_name} -[{edge_type}]-> {to_name}: {exc}")
            return False

    # ── Background metrics refresh ─────────────────────────────────────────────

    async def compute_graph_metrics(self) -> int:
        """
        Recompute downstream_count and is_single_point_of_failure for all Concept nodes.
        Must run after every dependency graph change.
        Returns number of nodes updated.
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(_RECOMPUTE_DOWNSTREAM_COUNTS)
                summary = await result.consume()
                count = summary.counters.properties_set // 2  # 2 props set per node
                logger.info(f"Graph metrics recomputed: ~{count} nodes updated")
                return count
        except Exception as exc:
            logger.error(f"compute_graph_metrics failed: {exc}")
            return 0

    # ── Coverage metrics ───────────────────────────────────────────────────────

    async def get_coverage_metrics(self) -> dict[str, Any]:
        """Returns data quality metrics for the Impact Dashboard."""
        try:
            async with self._driver.session() as session:
                result = await session.run("""
                    MATCH (loc:Concept {entityType: 'LOCATION'})
                    OPTIONAL MATCH (loc)-[:HOSTS]->(dep:Concept)
                    WITH loc, count(DISTINCT dep) AS direct_deps
                    RETURN
                        count(loc) AS total_locations,
                        count(CASE WHEN direct_deps > 0 THEN loc END) AS locations_with_deps,
                        toFloat(count(CASE WHEN direct_deps > 0 THEN loc END)) /
                          CASE WHEN count(loc) > 0 THEN toFloat(count(loc)) ELSE 1.0 END AS coverage_score
                """)
                record = await result.single()
                if not record:
                    return {"total_locations": 0, "locations_with_deps": 0, "coverage_score": 0.0}

                coverage = float(record["coverage_score"] or 0.0)
                return {
                    "total_locations": record["total_locations"],
                    "locations_with_deps": record["locations_with_deps"],
                    "coverage_score": round(coverage * 100, 1),
                    "target_coverage": 85.0,
                    "is_operational_ready": coverage >= 0.85,
                }
        except Exception as exc:
            logger.error(f"get_coverage_metrics failed: {exc}")
            return {"error": str(exc)}
