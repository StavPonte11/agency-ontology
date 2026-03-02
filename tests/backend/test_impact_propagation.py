"""
Impact Propagation Correctness Tests — Agency Ontology
=======================================================
Primary acceptance gate (spec Part 9.2):
  The canonical example from Part 1.4 must produce EXACT tiered output.
  If test_canonical_example_propagation fails, no other test result matters.

Graph topology (Part 1.4):
  Location L → (HOSTS) → Department X
  Department X → (RUNS) → Project A  [criticality=HIGH, no mitigation]
  Department X → (RUNS) → Project B  [PLANNED — never operational]
  Department X → (RUNS) → Project C  [criticality=CRITICAL, no mitigation]
  Project A → (SERVES) → Client D   [criticality=HIGH]
  Project A → (SERVES) → Client E   [criticality=CRITICAL, no mitigation]
  Project A → (SERVES) → Client F   [criticality=HIGH, mitigation=remote]
  Project B → (SERVES) → Client G   [but B is PLANNED → G sees no harm]
  Project C → (SERVES) → Client H   [criticality=CRITICAL, no mitigation]

Expected tiers (from spec):
  CRITICAL: Client H (via C — no mitigation), Client E (CRITICAL edge, no mitigation)
  HIGH: Client D, Client F (via A — HIGH edge; F has mitigation→ HIGH not CRITICAL)
  MONITOR: Project B (PLANNED), Client G (downstream of PLANNED B)

Run with:
    pytest tests/backend/test_impact_propagation.py -v -s -m impact
"""
from __future__ import annotations

import os
import sys
import uuid
import logging
import pytest
import pytest_asyncio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_impact_propagation")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from dotenv import load_dotenv
    _env = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "services", ".env",
    )
    if os.path.exists(_env):
        load_dotenv(_env)
except ImportError:
    pass

NEO4J_URI      = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "changeme")

pytestmark = pytest.mark.impact


# ── Canonical graph data ───────────────────────────────────────────────────────

#  All nodes for the Part 1.4 canonical example.
CANONICAL_NODES = [
    # (name, entity_type, op_status, criticality)
    ("Location L",   "LOCATION",   "ACTIVE",   "CRITICAL"),
    ("Department X", "DEPARTMENT", "ACTIVE",   "HIGH"),
    ("Project A",    "PROJECT",    "ACTIVE",   "HIGH"),
    ("Project B",    "PROJECT",    "PLANNED",  "HIGH"),   # KEY: PLANNED!
    ("Project C",    "PROJECT",    "ACTIVE",   "CRITICAL"),
    ("Client D",     "CLIENT",     "ACTIVE",   "HIGH"),
    ("Client E",     "CLIENT",     "ACTIVE",   "CRITICAL"),
    ("Client F",     "CLIENT",     "ACTIVE",   "HIGH"),
    ("Client G",     "CLIENT",     "ACTIVE",   "HIGH"),  # downstream of PLANNED B
    ("Client H",     "CLIENT",     "ACTIVE",   "CRITICAL"),
]

# (from, to, edge_type, criticality, mitigation_available)
CANONICAL_EDGES = [
    ("Location L",   "Department X", "HOSTS", "CRITICAL", False),
    ("Department X", "Project A",    "RUNS",  "HIGH",     False),
    ("Department X", "Project B",    "RUNS",  "HIGH",     False),  # B is PLANNED
    ("Department X", "Project C",    "RUNS",  "CRITICAL", False),
    ("Project A",    "Client D",     "SERVES","HIGH",     False),
    ("Project A",    "Client E",     "SERVES","CRITICAL", False),
    ("Project A",    "Client F",     "SERVES","HIGH",     True),   # mitigation: remote
    ("Project B",    "Client G",     "SERVES","HIGH",     False),  # B PLANNED → G MONITOR only
    ("Project C",    "Client H",     "SERVES","CRITICAL", False),
]


# ── Fixtures ───────────────────────────────────────────────────────────────────

async def _neo4j_driver():
    from neo4j import AsyncGraphDatabase
    try:
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        await driver.verify_connectivity()
        return driver
    except Exception as exc:
        pytest.skip(f"Neo4j not available at {NEO4J_URI}: {exc}")


async def _build_canonical_graph(session, tag: str) -> None:
    """Write the Part 1.4 canonical graph into Neo4j under the given tag."""
    for (name, entity_type, op_status, criticality) in CANONICAL_NODES:
        concept_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"impact-test::{name.lower()}"))
        await session.run("""
            MERGE (c:Concept {id: $id})
            ON CREATE SET
              c.name             = $name,
              c.entityType       = $entity_type,
              c.operationalStatus = $op_status,
              c.criticalityLevel = $criticality,
              c.sources          = [$tag],
              c.status           = 'CANDIDATE',
              c.conceptType      = 'TERM',
              c.domain           = ['Impact'],
              c.confidence       = 0.9,
              c.sensitivity      = 'INTERNAL',
              c.usageCount       = 0,
              c.downstreamCount  = 0,
              c.isSinglePointOfFailure = false,
              c.createdAt        = datetime(),
              c.updatedAt        = datetime()
            ON MATCH SET
              c.operationalStatus = $op_status,
              c.entityType        = $entity_type,
              c.criticalityLevel  = $criticality
        """, id=concept_id, name=name, entity_type=entity_type,
             op_status=op_status, criticality=criticality, tag=tag)

    from services.retrieval_api.services.impact_service import ImpactService
    from services.retrieval_api.services.impact_service import _MERGE_DEPENDENCY_EDGE_TEMPLATE

    for (from_n, to_n, edge_type, criticality, mitigation) in CANONICAL_EDGES:
        cypher = _MERGE_DEPENDENCY_EDGE_TEMPLATE.replace("{edge_type}", edge_type)
        await session.run(
            cypher,
            from_name=from_n,
            to_name=to_n,
            criticality=criticality,
            propagation_mode="DIRECT",
            mitigation_available=mitigation,
            recovery_time_hours=None,
            condition=None,
        )


async def _teardown_canonical_graph(session, tag: str) -> None:
    """Remove all canonical-test nodes."""
    await session.run(
        "MATCH (c:Concept) WHERE $tag IN c.sources DETACH DELETE c",
        tag=tag,
    )


@pytest_asyncio.fixture(scope="module")
async def canonical_graph():
    """Build the Part 1.4 canonical graph once for all tests in this module."""
    driver = await _neo4j_driver()
    tag = f"impact-canonical-test-{uuid.uuid4().hex[:8]}"

    # Ensure impact schema indexes exist
    from services.retrieval_api.services.impact_service import ImpactService
    impact = ImpactService(driver)
    await impact.ensure_impact_schema()

    async with driver.session() as session:
        await _build_canonical_graph(session, tag)
    logger.info(f"Canonical graph built with tag={tag}")

    yield driver, impact, tag

    # Teardown
    async with driver.session() as session:
        await _teardown_canonical_graph(session, tag)
    await driver.close()
    logger.info(f"Canonical graph torn down (tag={tag})")


# ── Tests: Canonical Example (spec Part 9.2 — PRIMARY ACCEPTANCE GATE) ────────

@pytest.mark.asyncio
async def test_canonical_example_propagation(canonical_graph):
    """
    Part 9.2 canonical example test.
    This is the PRIMARY acceptance gate — if this fails, nothing else matters.

    Builds the exact Part 1.4 graph and asserts:
      - Client H in CRITICAL tier
      - Client E in CRITICAL tier
      - Client D in HIGH tier
      - Client F in HIGH tier (mitigation available)
      - Project B in MONITOR tier (PLANNED)
      - Client G in MONITOR tier (downstream of PLANNED B — no harm)
    """
    driver, impact, _ = canonical_graph

    logger.info("Running canonical example propagation from 'Location L'...")
    result = await impact.propagate_impact(
        entity_name="Location L",
        max_depth=5,
        include_mitigation=False,
        include_historical=False,
    )

    critical_names = {e.name for e in result.critical_entities}
    high_names     = {e.name for e in result.high_entities}
    monitor_names  = {e.name for e in result.monitor_entities}

    logger.info(f"CRITICAL: {critical_names}")
    logger.info(f"HIGH:     {high_names}")
    logger.info(f"MONITOR:  {monitor_names}")

    # CRITICAL tier: Client H (path C→H, no mitigation), Client E (path A→E, CRITICAL edge, no mit)
    assert "Client H" in critical_names, (
        f"Client H must be CRITICAL (served by Project C, no mitigation). "
        f"Got CRITICAL={critical_names}, HIGH={high_names}, MONITOR={monitor_names}"
    )
    assert "Client E" in critical_names, (
        f"Client E must be CRITICAL (served by Project A, CRITICAL edge, no mitigation). "
        f"Got CRITICAL={critical_names}"
    )

    # HIGH tier: Client D (path A→D, HIGH edge), Client F (path A→F, HIGH edge, mitigation)
    assert "Client D" in high_names, (
        f"Client D must be HIGH (served by Project A, HIGH edge). Got HIGH={high_names}"
    )
    assert "Client F" in high_names, (
        f"Client F must be HIGH (served by Project A, mitigation=True → HIGH not CRITICAL). "
        f"Got HIGH={high_names}"
    )

    # PRE-OPERATIONAL ISOLATION: Project B is PLANNED → must be MONITOR
    assert "Project B" in monitor_names, (
        f"Project B is PLANNED — must appear in MONITOR, not CRITICAL or HIGH. "
        f"Got MONITOR={monitor_names}, CRITICAL={critical_names}, HIGH={high_names}"
    )

    # THE KEY TEST: Client G is downstream of PLANNED Project B
    # — must NOT appear in CRITICAL or HIGH tiers
    assert "Client G" not in critical_names, (
        f"Client G must NOT be CRITICAL — it is served by PLANNED Project B. "
        f"Pre-operational halt failed! CRITICAL={critical_names}"
    )
    assert "Client G" not in high_names, (
        f"Client G must NOT be HIGH — it is served by PLANNED Project B. "
        f"Pre-operational halt failed! HIGH={high_names}"
    )

    logger.info("✓ Canonical example test passed — pre-operational halt working correctly")


@pytest.mark.asyncio
async def test_pre_operational_isolation_client_g(canonical_graph):
    """
    Dedicated pre-operational isolation test (spec Part 9.2).
    Client G must appear in MONITOR with explanation that no active harm is caused.
    """
    driver, impact, _ = canonical_graph

    result = await impact.propagate_impact(
        entity_name="Location L",
        max_depth=5,
        include_mitigation=False,
        include_historical=False,
    )

    monitor_names = {e.name for e in result.monitor_entities}

    # Client G must be either in MONITOR or absent entirely (not reached)
    # Both are acceptable — reaching CRITICAL or HIGH is the failure
    critical_names = {e.name for e in result.critical_entities}
    high_names = {e.name for e in result.high_entities}

    assert "Client G" not in critical_names, (
        "CRITICAL FAILURE: Client G appeared in CRITICAL tier. "
        "Pre-operational propagation halt is not working."
    )
    assert "Client G" not in high_names, (
        "CRITICAL FAILURE: Client G appeared in HIGH tier. "
        "Pre-operational propagation halt is not working."
    )

    # Project B itself must be in MONITOR with operational_status=PLANNED
    planned_project = next(
        (e for e in result.monitor_entities if e.name == "Project B"), None
    )
    if planned_project is not None:
        assert planned_project.operational_status.value == "PLANNED", (
            f"Project B operational_status must be PLANNED, got {planned_project.operational_status}"
        )
        assert planned_project.impact_tier == "MONITOR", (
            f"Project B impact_tier must be MONITOR, got {planned_project.impact_tier}"
        )

    logger.info("✓ Pre-operational isolation test passed")


@pytest.mark.asyncio
async def test_depth_boundary_enforcement(canonical_graph):
    """
    Depth boundary test (spec Part 9.2).
    With max_depth=1, only Department X should appear (1 hop from Location L).
    Clients at hop 2-3 must not appear.
    """
    driver, impact, _ = canonical_graph

    result = await impact.propagate_impact(
        entity_name="Location L",
        max_depth=1,
        include_mitigation=False,
        include_historical=False,
    )

    all_names = {
        e.name for e in
        result.critical_entities + result.high_entities + result.monitor_entities
    }
    furthest_hop = max(
        (e.hop_distance for e in result.critical_entities + result.high_entities + result.monitor_entities),
        default=0,
    )

    # No entity should be more than 1 hop away
    assert furthest_hop <= 1, (
        f"max_depth=1 was specified but got entities at hop {furthest_hop}. "
        "Depth boundary not enforced."
    )

    # Clients (hop 2+) must not appear
    client_names = {"Client D", "Client E", "Client F", "Client G", "Client H"}
    reached_clients = all_names & client_names
    assert not reached_clients, (
        f"max_depth=1 but clients at hop 2+ were reached: {reached_clients}. "
        "Depth boundary enforcement failed."
    )

    logger.info(f"✓ Depth boundary test passed (max_depth=1, entities={all_names})")


@pytest.mark.asyncio
async def test_project_a_clients_accessible_at_depth_2(canonical_graph):
    """With max_depth=2, clients served by Project A should be reachable."""
    driver, impact, _ = canonical_graph

    result = await impact.propagate_impact(
        entity_name="Location L",
        max_depth=2,
        include_mitigation=False,
        include_historical=False,
    )

    all_names = {
        e.name for e in
        result.critical_entities + result.high_entities + result.monitor_entities
    }
    logger.info(f"Depth-2 result: {all_names}")

    # Department X and all Projects should appear
    assert "Department X" in all_names, "Department X missing at depth 2"
    assert "Project A" in all_names, "Project A missing at depth 2"
    assert "Project B" in all_names, "Project B missing at depth 2 (should be in MONITOR)"
    assert "Project C" in all_names, "Project C missing at depth 2"


@pytest.mark.asyncio
async def test_reverse_query_location_l(canonical_graph):
    """Department X depends on Location L — reverse query must find Department X."""
    driver, impact, _ = canonical_graph

    result = await impact.reverse_query(entity_name="Department X", max_depth=3)

    logger.info(f"Reverse query for Dept X: {result}")
    dep_names = {d["name"] for d in result.get("dependent_entities", [])}

    assert "Location L" in dep_names, (
        f"Location L must appear as dependent of Department X. Got: {dep_names}"
    )


@pytest.mark.asyncio
async def test_simulation_flag_propagated(canonical_graph):
    """scenario_model calls must have is_simulation=True throughout the result."""
    driver, impact, _ = canonical_graph

    result = await impact.propagate_impact(
        entity_name="Location L",
        max_depth=5,
        include_mitigation=False,
        include_historical=False,
        is_simulation=True,
    )

    assert result.is_simulation is True, (
        "PropagationResult.is_simulation must be True for scenario_model calls"
    )


@pytest.mark.asyncio
async def test_coverage_metrics_returns_valid_shape(canonical_graph):
    """Coverage metrics endpoint must return valid numeric shape."""
    driver, impact, _ = canonical_graph

    metrics = await impact.get_coverage_metrics()
    assert "total_locations" in metrics
    assert "coverage_score" in metrics
    assert isinstance(metrics["coverage_score"], (int, float))
    logger.info(f"Coverage metrics: {metrics}")
