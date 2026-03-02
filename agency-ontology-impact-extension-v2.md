# PROMPT EXTENSION: Impact Analysis & Consequence Mapping System
## Add-on to: Agency Ontology System v2 + Hierarchy Extension
## Orientation: Use-Case Definition · Domain Model · Execution Plan · Tests & Evaluation

---

## FRAMING: WHAT KIND OF PROBLEM THIS IS

The Agency Ontology already answers: **"What does X mean in our organization?"**
This extension answers a structurally different question:

> **"If X becomes unavailable — what breaks downstream, who is hurt, how severely,
> and what should we do about it?"**

This is not a lookup problem. It is a **propagation problem**: tracing consequence
chains forward through a dependency graph from a trigger point, assigning severity and
mitigation options at each hop, and producing an actionable intelligence report.

The specific trigger in this extension is a **Location** becoming unavailable or
compromised. But the propagation engine must be generic enough to support any entity
as a trigger — a system going offline, a department losing key personnel, a project
being cancelled — because real-world consequence mapping needs this flexibility.

The system will be queried by analysts, decision-makers, and agents in natural language.
It must respond with structured, tiered, actionable assessments — not just lists of
affected entities, but a clear prioritization of what needs immediate attention, what
can wait, and what the historical precedent says about how to handle it.

---

## PART 1 — THE DOMAIN MODEL

### 1.1 Core Intuition: The Five-Layer Impact Stack

Every impact scenario in this domain follows the same propagation structure.
Understand this structure first — it shapes every design decision downstream.

```
LAYER 1 -- TRIGGER
           A Location is unavailable, compromised, or degraded.
           This is always the root of the propagation.

LAYER 2 -- DIRECT OCCUPANTS
           Departments, units, assets, systems, and personnel
           physically or operationally bound to that Location.
           These are the first-order casualties.

LAYER 3 -- OPERATIONAL ENTITIES
           Projects, programs, processes, and services
           that Layer 2 entities are actively running.
           Some are operational. Some are planned but not yet active.
           This distinction is critical — it determines whether real harm occurs.

LAYER 4 -- DOWNSTREAM STAKEHOLDERS
           Clients, partners, contracts, SLAs, and deliverables
           that depend on Layer 3 entities being operational.
           These are the entities that experience external harm.

LAYER 5 -- SYSTEMIC CONSEQUENCES
           Regulatory, financial, strategic, or reputational effects
           that compound from sustained Layer 4 impact.
           The long tail — often invisible until too late.
```

The system must traverse this stack completely and accurately.
It must also traverse it intelligently — not every path propagates,
not every entity is harmed equally, and operational status determines
whether a chain continues or terminates.

### 1.2 Entity Taxonomy

These are the entity types in the impact domain. They map onto Concept nodes
in the existing ontology — this extension adds operational properties and
typed dependency edges on top of existing semantic knowledge.

```
LOCATION      The anchor of all impact scenarios.
              A physical building, base, zone, logical site, or network segment.
              Key properties: operational_status, criticality_tier,
                              backup_location (reference to another Location),
                              capacity, region.

DEPARTMENT    An organizational unit that operates from one or more locations.
              Key properties: head_count, function_type, operational_status,
                              can_operate_remotely (boolean — critical for mitigation).

PROJECT       A bounded initiative run by a department or cross-functional team.
              Key properties: operational_status (ACTIVE | PLANNED | SUSPENDED | CLOSED),
                              criticality (CRITICAL | HIGH | MEDIUM | LOW),
                              deadline, has_active_clients (boolean).
              The PLANNED/not-yet-operational distinction is the most important
              property in the entire system. A PLANNED project that is disrupted
              experiences a delay, not a harm — its downstream clients are unaffected.

CLIENT        An internal or external stakeholder served by one or more projects.
              Key properties: tier (TIER_1 | TIER_2 | TIER_3),
                              sla_breach_hours, contract_type.

ASSET         Physical or digital equipment bound to a location.
              Key properties: asset_type, has_backup (boolean),
                              backup_asset_ref, redundancy_type.

SYSTEM        A software, infrastructure, or communications system.
              Key properties: system_type, has_failover (boolean),
                              failover_time_hours, is_shared (boolean -- used by many).

PROCESS       A recurring operational procedure.
              Key properties: frequency, has_manual_fallback (boolean).

PERSONNEL     Key individuals whose absence creates a single point of failure.
              Not all staff — only those without a functional backup.
              Key properties: role, has_designated_backup (boolean).

OBLIGATION    An SLA, contract clause, or regulatory deadline.
              Key properties: deadline, breach_penalty, regulatory_authority.
```

### 1.3 Dependency Relationship Taxonomy

The typed edges that connect entities in the dependency graph.
Every edge carries: criticality, propagation_mode, mitigation_available,
recovery_time_hours, and optionally a condition string.

```
HOSTS              Location -> Department | Asset | System | Personnel
RUNS               Department -> Project | Process
OPERATES           Department -> Asset | System
SERVES             Project -> Client | Obligation
USES               Project | Process -> Asset | System
REPORTS_TO         Department -> Department  (escalation path)
BACKUP_FOR         Asset | Location | System -> Asset | Location | System
FEEDS              System -> System  (data or information dependency)
BLOCKS             Project -> Project  (sequencing dependency)
STAFFED_BY         Department | Project -> Personnel  (key person dependency)
```

The most important edge properties:

```
criticality:
  CRITICAL   -- the downstream entity cannot function at all without this dependency.
               Disruption is immediate and total.
  HIGH       -- significant degradation. A workaround may exist but is costly.
  MEDIUM     -- moderate impact, manageable with standard fallback procedures.
  LOW        -- minor inconvenience, absorbed without meaningful consequence.
  NEGLIGIBLE -- no real operational impact.

propagation_mode:
  DIRECT      -- impact is immediate and certain when the source is disrupted.
  CONDITIONAL -- impact depends on a condition.
  TIME_DELAYED -- impact appears after N hours or days.
  PARTIAL     -- only some functions are affected, not all.

mitigation_available: boolean
  Whether a documented workaround, backup, or fallback exists for this specific edge.

recovery_time_hours:
  Estimated time to restore this specific dependency link.
```

### 1.4 The Canonical Worked Example

This is the exact scenario from the problem statement, fully modeled.
The coding agent must reproduce this propagation output correctly.
It is used as the primary acceptance test in Part 9.

```
Trigger: Location L is unavailable.

Step 1 -- Direct occupants (Layer 2):
  Location L -[HOSTS, CRITICAL]-> Department X
  Location L -[HOSTS, HIGH]->     Asset A1 (Communications Server, no backup)

Step 2 -- Department X's operational entities (Layer 3):
  Department X -[RUNS, CRITICAL]-> Project A  (status: ACTIVE, criticality: HIGH)
  Department X -[RUNS, HIGH]->     Project B  (status: PLANNED, criticality: MEDIUM)
  Department X -[RUNS, CRITICAL]-> Project C  (status: ACTIVE, criticality: CRITICAL)

Step 3 -- Downstream stakeholders (Layer 4):
  Project A -[SERVES]-> Client D  (Tier-2, SLA: 48h)
  Project A -[SERVES]-> Client E  (Tier-1, SLA: 24h)  <-- SLA breach risk
  Project A -[SERVES]-> Client F  (Tier-3, SLA: 72h)
  Project B -[SERVES]-> Client G  (Tier-2)             <-- CHAIN STOPS: Project B is PLANNED
  Project C -[SERVES]-> Client H  (Tier-1, SLA: 12h)  <-- Critical, breach imminent

Expected propagation output:

  CRITICAL / IMMEDIATE:
  - Project C -> Client H: CRITICAL project, Tier-1 client, 12h SLA. No mitigation.
    Action: invoke emergency SLA clause immediately.
  - Asset A1: no backup, 6 departments depend on it. Critical bridge node.
    Action: activate backup communications at Location N.

  HIGH / TIME-SENSITIVE:
  - Project A -> Client E: active project, Tier-1, 24h SLA.
    Mitigation available: partial remote operation from Location M.
  - Project A -> Clients D and F: active project, lower tiers. SLA buffer exists.

  LOW HARM / MONITOR ONLY:
  - Project B -> Client G: Project B is PLANNED, not yet operational.
    Client G is not actively being served. Impact = delay to future go-live only.
    No client notification required.

  RECOMMENDED ACTIONS (in priority order):
  1. Activate backup comms at Location N for Asset A1.
  2. Contact Client H (Project C) to invoke emergency SLA clause.
  3. Redirect Department X critical staff to Location M for Projects A and C.
  4. Formally notify Client E of SLA risk on Project A.
  5. Log Project B go-live delay -- update timeline, no external notification needed.
```

---

## PART 2 -- USE CASES

### Use Case 1: Full Impact Assessment from a Location

Who asks: Situation room analyst, operations commander, emergency coordinator.

Trigger: A location name is provided, with or without a disruption type
(physical damage, power loss, access denial, communications failure, cyber incident).

What the system returns: Every downstream entity organized by layer and criticality;
for each entity: hop distance, propagation path, mitigation status, estimated recovery
time, and whether it is a critical bridge node; a tiered action list; a natural language
situation report; and relevant historical incidents.

Example queries:
- "Location Alpha is inaccessible. Full impact assessment."
- "We have lost access to Site 7. What breaks and who do I call first?"
- "Building 4 is offline due to a power failure. Situation report."

### Use Case 2: Reverse Dependency Query

Who asks: Change manager, IT operations, maintenance planner.

Trigger: Any entity (not necessarily a location) as the subject.

What the system returns: All entities that depend on the queried entity, ranked by
downstream exposure. Identifies whether the entity is a single point of failure.

Example queries:
- "System ARGUS is going down for maintenance Sunday. Who is affected?"
- "What depends on Department X? Can we restructure it safely?"
- "If we decommission Asset 12, what breaks?"

### Use Case 3: Risk Comparison Across Locations

Who asks: Business continuity planner, resource allocator, executive.

Trigger: A request to compare or rank multiple locations by blast radius.

What the system returns: Locations ranked by total downstream impact score,
with breakdown by critical projects, Tier-1 client exposure, and SPOF assets.

Example queries:
- "Which location is our biggest single point of failure?"
- "If we had to temporarily close one of Sites 3, 7, or 12, which causes least disruption?"
- "Rank our locations by operational risk."

### Use Case 4: Mitigation Planning

Who asks: Crisis manager, operations coordinator.

Trigger: A critical impact has been identified and options are needed.

What the system returns: For each affected critical entity, ranked mitigation options
drawn from: documented backup locations, redundant assets, alternative departments,
and historical precedent showing what was done in past similar situations.

Example queries:
- "Location Alpha is down and Project ATLAS is critical. What are our options?"
- "Client H is at SLA risk. What can we do in the next 6 hours?"

### Use Case 5: Historical Context and Precedent

Who asks: Any analyst during an active incident or planning session.

Trigger: A question about past incidents involving the same locations or entities.

What the system returns: Matching past incidents, what actions were taken,
recovery time, and lessons recorded.

Example queries:
- "Has this happened before with Location Alpha?"
- "How did we handle the last time Department X was disrupted?"

### Use Case 6: What-If Scenario Modeling

Who asks: Planner, exercise designer, policy reviewer.

Trigger: A hypothetical scenario, explicitly flagged as simulation.
No alerts generated, no state written.

What the system returns: Same as Use Case 1, clearly marked as SIMULATION.

Example queries:
- "Hypothetically, if both Alpha and Beta were simultaneously unavailable, what is the combined impact?"
- "War-game scenario: we lose Sites 3 and 7. Model the full downstream effect."

---

## PART 3 -- DATA SOURCES

### 3.1 Primary Source: The Excel Dependency File

What it is: A structured spreadsheet mapping locations to their direct dependencies.
The exact column schema is unknown at development time. Treat it as semi-structured —
it was written by humans for humans, not for machines.

Expected messiness: dependencies may be in a single free-text column or split across
multiple columns; the same entity may be named differently across rows; merged cells,
multi-sheet workbooks, and rows serving as section headers are all possible; some rows
will have partial data.

What the system must do:

First, detect the schema without assuming it. Before any extraction runs, a schema
detection pass reads all column names, samples values from the first 20 rows, and
produces a DetectedSchema report identifying the location column, description columns,
and dependency columns. This report is shown to the operator in the UI for confirmation
before ingestion runs. The operator can override any column mapping.

Second, parse each row into a structured location record with raw dependency strings.
Location name and description are extracted deterministically. Dependency strings
require LLM extraction to identify entity types, entity names, and relationships.

Third, resolve every extracted entity name against the existing ontology graph using
the same three-layer resolution already in the pipeline (exact, fuzzy, semantic).
An entity named "Dept. Intelligence" that matches the existing concept
"Intelligence Analysis Department" must be linked, not duplicated.

Fourth, infer the dependency edges. When the Excel file says "Location L hosts
Department X and Asset A", produce:
Location L -[HOSTS]-> Department X and Location L -[HOSTS]-> Asset A.
When it says "Department X runs Projects A, B, C", produce three RUNS edges.
Project operational status must be inferred from description or flagged for
human confirmation if ambiguous.

What the system must never do: silently discard any row. Every row produces either
a committed result or a Review Queue item. Silent discards are a data integrity failure.

### 3.2 Secondary Source: Historical Knowledge Files

What they are: A collection of unstructured files (PDFs, Word documents, plain text)
containing records of past incidents, after-action reports, lessons learned, business
continuity plans, and historical project and client records.

The value they add: when an analyst asks "what do we do?", the system can respond
"the last time this happened (2022), we activated the backup at Location Beta and
contacted Client H directly — recovery took 18 hours." This transforms the system
from a dependency map into institutional memory.

How to ingest: run through the existing PDF pipeline with an additional extraction
focus on incidents. The LLM extraction model looks specifically for: named incidents
with dates and affected locations; actions taken and by whom; outcome including
recovery time; and lessons explicitly recorded.

These are not stored as Concept nodes. They are stored as HistoricalIncident nodes
linked to the location and entity nodes they reference. They are retrieved when their
linked locations or entities match the current impact query.

### 3.3 Future Sources (Architecture Must Accommodate)

The connector interface must accommodate these without pipeline architecture changes:
CMDB and IT Asset Management systems for automated asset dependency data;
HR systems for personnel node data and backup assignments;
Project management systems for live project status;
GIS systems for spatial location data.
These are future additions — they require only a new SourceConnector implementation.

---

## PART 4 -- INTEGRATION WITH THE EXISTING ONTOLOGY SYSTEM

### Relationship Between Impact Layer and Semantic Layer

The existing ontology answers "what does X mean?" using Concept nodes and semantic
relationships. The impact layer adds "what does X do?" and "what does X depend on?"
on top of those same nodes.

This is not a separate graph. Every Location, Department, Project, Client, Asset, and
System in the impact domain is also a Concept node in the existing ontology.
The extension adds:
1. Operational properties on existing Concept nodes (status, criticality, SLA fields)
2. New typed dependency relationship types (HOSTS, RUNS, SERVES, etc.)
3. A new HistoricalIncident node type (not a Concept -- standalone)
4. Pre-computed graph metrics on key nodes (downstream_count, is_single_point_of_failure)

The existing ontology_lookup and ontology_enrich MCP tools continue to work unchanged.
The new impact_* MCP tools work alongside them, traversing operational-typed edges.

The ontology hierarchy, entity resolution, and multilingual labels all benefit the
impact system automatically. When an agent looks up a Hebrew codename to find its
dependencies, the existing label resolution handles the term lookup, and the impact
system handles the propagation.

### Enrichment Middleware Extension

Extend the orchestrator's existing AgentContextEnrichmentMiddleware:

When enriched context contains any Location concepts, automatically append to the
system prompt: the location's criticality_tier, downstream_entity_count, and
is_single_point_of_failure flag.

This means any time an agent encounters a location name in a user query, it has
enough context to decide whether to call impact_propagate before the user explicitly
asks for an impact assessment.

---

## PART 5 -- NEW MCP TOOLS

### impact_propagate
The primary tool. Given a trigger entity (typically a Location), compute the full
downstream impact chain.

Input: entity name, disruption type (optional), max depth (default 5),
include mitigation (default true), include historical context (default true).

Output: tiered list of all impacted entities with path, criticality, mitigation status,
and recovery estimate; entities requiring immediate action; critical bridge nodes;
natural language situation report; relevant historical incidents.

When to call: whenever a user describes a location or entity becoming unavailable,
compromised, or disrupted. Also for planning scenarios with hypothetical=false.

### impact_reverse_query
Answers "what depends on this?" Finds all entities whose operation requires the queried
entity to be available.

Input: entity name, entity type (optional), max depth (default 3).
Output: all dependent entities ranked by downstream exposure; single-point-of-failure flag.

When to call: maintenance planning, change management, decommissioning decisions.

### impact_compare_locations
Compares blast radius of multiple locations for prioritization and continuity planning.

Input: location names (list), comparison metric.
Output: ranked comparison with per-location breakdown.

When to call: "which location is most critical?", "least disruptive to close?", risk ranking.

### impact_find_mitigations
Given an affected entity, retrieves all known mitigation options.

Input: entity name, scenario context (free text).
Output: ranked mitigation options with source (documented backup, historical precedent,
alternative entity with capability to absorb the function).

When to call: when critical entities are flagged with no automatic mitigation,
or when the analyst explicitly asks what can be done.

### impact_historical_context
Retrieves past incidents involving the same locations or entities.

Input: entity names (list), location names (list), since date (optional).
Output: matching incidents with date, actions taken, outcome, recovery time, lessons recorded.

When to call: "has this happened before?", "track record", "precedent" queries.

### impact_scenario_model
Identical to impact_propagate but for hypothetical scenarios.
Writes no state, triggers no alerts. Output is clearly labeled SIMULATION.

Input: same as impact_propagate plus hypothetical: true.
Output: same as impact_propagate, labeled as SIMULATION throughout.

When to call: queries with "what if", "hypothetically", "suppose", "war game", "exercise".

---

## PART 6 -- AGENT DECISION LOGIC

### Routing Decision Tree

```
User message received
|
+--> STEP 1: ontology_enrich(message)
|    Extract all entity and location mentions.
|    Identify Location nodes in enriched context.
|
+--> STEP 2: Classify query intent
     |
     +-- DISRUPTION INTENT
     |   ("unavailable", "offline", "compromised", "lost access",
     |    "affected", "down", "closed", "cannot reach")
     |       --> impact_propagate(location or entity)
     |           If hypothetical language: impact_scenario_model() instead
     |
     +-- DEPENDENCY INTENT
     |   ("what depends on", "who uses", "what relies on",
     |    "what breaks if", "downstream of")
     |       --> impact_reverse_query(entity)
     |
     +-- COMPARISON INTENT
     |   ("which location", "rank", "worst case", "most critical",
     |    "least disruptive", "compare sites")
     |       --> impact_compare_locations(locations)
     |
     +-- MITIGATION INTENT
     |   ("what can we do", "options", "how do we fix",
     |    "workaround", "alternative", "keep running")
     |       --> impact_find_mitigations(entity, context)
     |
     +-- HISTORICAL INTENT
     |   ("has this happened", "last time", "precedent", "track record")
     |       --> impact_historical_context(entities, locations)
     |
     +-- COMBINED (most real queries)
             --> Chain: impact_propagate -> impact_find_mitigations
                                        -> impact_historical_context
                Return a unified response addressing all aspects.
```

### Situation Report Output Format

The natural language summary for every propagation result must follow this structure.
Generated by the LLM -- not by template concatenation -- but the LLM must be
explicitly prompted to produce this specific shape:

```
[IMPACT ASSESSMENT -- {Location Name} -- {Timestamp}]

SITUATION:
{2-3 sentences: what happened, what is directly affected, overall severity.}

CRITICAL -- IMMEDIATE ACTION REQUIRED:
{Numbered list. CRITICAL entities with no available mitigation only.
Each item: entity name, why it is critical, specific action needed, time window.}

HIGH -- TIME-SENSITIVE:
{Numbered list. HIGH entities. Include available mitigation if known.}

MONITOR -- NO IMMEDIATE ACTION:
{Brief list. Pre-operational entities, low-criticality impacts, well-mitigated items.
Explain WHY they do not need immediate action.
Example: "Project B is pre-operational, Client G is not yet being served,
impact is delay to future go-live only."}

HISTORICAL CONTEXT:
{If found: most relevant past incident and outcome. One paragraph.}
{If not found: "No closely matching historical incidents found in knowledge base."}

CONFIDENCE: {HIGH | MEDIUM | LOW}
{One sentence explaining the rating.
Example: "MEDIUM: dependency data for 3 of 8 directly hosted entities is incomplete."}
```

---

## PART 7 -- UI ADDITIONS

New routes under /ontology/impact/ in the Agency portal module.

### View 1: Impact Dashboard (/ontology/impact)

Shows the state of the impact graph at a glance.

Risk heat map: locations plotted against impact dimensions (critical project count,
Tier-1 client exposure, SPOF asset count). Click any cell to drill into that location.

Critical bridges panel: top N entities across the entire graph with the highest
downstream_count combined with is_single_point_of_failure=true.

Recent queries feed: last 20 propagation queries run by agents or analysts,
each with a one-line result summary.

Data coverage gauge: percentage of locations with complete, fully-resolved dependency
graphs. This must be prominently displayed -- incomplete dependency data directly
degrades impact assessment quality and analysts need to know its current reliability.

### View 2: Location Explorer (/ontology/impact/locations)

Full list of all locations with: criticality tier, direct dependency count,
total downstream entity count, data completeness score, last-assessed timestamp.
Click any location to open the Dependency Graph View.
Filter by: region, criticality, status, completeness level.

### View 3: Dependency Graph View (/ontology/impact/graph/:locationId)

The signature visualization. A React Flow canvas showing the dependency graph
rooted at a specific location.

Layout: layered left-to-right, one column per hop distance.
Location is always leftmost. Downstream entities cascade rightward.

Node visual encoding:
- Size proportional to downstream_count
- Color fill by operational status (green=ACTIVE, amber=PLANNED, red=SUSPENDED)
- Border thickness and color by criticality
- Icons by entity type
- Badges: warning for SPOF, lock for CRITICAL classification, check for mitigated

Edge visual encoding:
- Thickness by dependency criticality
- Style: solid=DIRECT, dashed=CONDITIONAL, dotted=TIME_DELAYED
- Color: red=no mitigation, green=mitigation available

Key interactions:
- Click any node: right panel shows entity detail, impact summary, historical incidents
- "Run Impact From Here": triggers propagation, highlights affected subgraph with animated pulse
- "Isolate Path" between two nodes: highlights shortest dependency path
- Toggle layers independently
- "Show Historical Incidents": overlays incident nodes as dated timeline markers

### View 4: Impact Query Runner (/ontology/impact/query)

Structured interface for analysts needing more control than conversational queries.
Location selector, disruption type selector, scope controls.
Results stream in real time as traversal completes.
Output tabs: Summary | By Layer | Critical Entities | Mitigations | Historical.
Export: PDF situation report, CSV of affected entities.

### View 5: Source Ingestion Manager (/ontology/impact/sources)

Excel file upload with schema detection preview.
Operator-adjustable column assignments before ingestion runs.
Per-row ingestion progress with warning and review item counts.
Entity resolution report: matched vs. new candidate vs. ambiguous.
Coverage report after ingestion.
Direct links from incomplete entries to the Review Queue.

---

## PART 8 -- EXECUTION PLAN

### Phase 1 -- Schema and Domain Model

Define all new entity types, edge types, and their properties.
Extend Neo4j with new node labels and dependency relationship types.
Extend Prisma with tables for impact job tracking.
Extend Elasticsearch index mappings for location and incident search.

Gate: Validate the schema against the actual Excel file before writing any pipeline code.
Every entity type and edge type must be grounded in at least 3 real rows from the
real data. Present the schema to the team and confirm it matches operational reality.

### Phase 2 -- Excel Connector and Ingestion

Build ExcelConnector as a SourceConnector implementation.
Build schema detection.
Build LLM extraction chain for dependency parsing using with_structured_output.
Build entity resolution pass against existing ontology.
Build edge inference logic.
Integrate with existing Kafka pipeline.
Integrate with Review Queue for low-confidence rows.

Gate: End-to-end ingestion test on the actual Excel file.
Measure entity extraction recall and precision, resolution accuracy, and idempotency.
See Part 9 for specific thresholds.

### Phase 3 -- Historical File Ingestion

Extend existing PDF pipeline with HistoricalIncident extraction model.
Link extracted incidents to location and entity nodes.

Gate: Run 10 historical context queries. Measure hit rate and relevance.
See Part 9 for thresholds.

### Phase 4 -- Propagation Engine

Build Neo4j propagation traversal query.
Build PropagationResult assembly service.
Build natural language summary generation chain.
Build mitigation finder.
Pre-compute downstream_count and is_single_point_of_failure as background jobs.

Gate: Propagation correctness tests. System must reproduce the exact tiered output
from the canonical worked example in Part 1.4. This is the non-negotiable acceptance test.

### Phase 5 -- MCP Tools and Orchestrator Integration

Register all six new impact MCP tools.
Extend enrichment middleware to flag Location nodes.
Test agent decision routing logic.

Gate: All six natural language test queries in Part 9 pass with correct tool selection.

### Phase 6 -- UI

Build five new views. Dependency Graph View is most complex -- allocate proportionally
more time. Test with actual data. Validate with at least one real analyst user.

### Phase 7 -- Hardening

Extend Grafana dashboards with impact-specific metrics.
Write k6 load tests for propagation queries.
Complete E2E test suite.
Write operator documentation for Excel schema configuration.

---

## PART 9 -- TESTS AND EVALUATION

### 9.1 Ingestion Quality Tests

Schema Detection Test:
Provide five differently-formatted versions of the Excel file: different column order,
different names, merged cells, multi-sheet, mixed-language headers.
Pass criterion: 5/5 correct identification of location column and dependency columns
without human correction.

Entity Extraction Recall and Precision:
For 20 manually reviewed rows from the real file, run LLM extraction and compare
to a ground-truth entity list prepared by a domain expert.
Pass criterion: Precision > 0.90, Recall > 0.85.

Entity Resolution Accuracy:
For 50 entity names extracted from the Excel file, compare automated resolution
to manually verified resolution.
Pass criterion: Overall accuracy > 0.88.
Critical sub-criterion: False merge rate < 0.03.
Two distinct entities merged into one is the highest-impact failure mode.

Idempotency Test:
Run full Excel ingestion twice on the same file.
Pass criterion: Graph state after second run is identical to after first run.
Zero new nodes or edges created on second run.

Partial Row Handling:
Provide 10 intentionally incomplete rows.
Pass criterion: All 10 produce a Review Queue item. Zero rows silently discarded.

### 9.2 Propagation Correctness Tests

Canonical Example Test:
Build the exact graph from Part 1.4. Run impact_propagate from Location L.
Pass criterion: Output exactly matches the expected tiered result.
This is non-negotiable. If this test fails, no other test result matters.

Pre-Operational Isolation Test:
Include a PLANNED project in the chain. Its downstream clients must not appear
in the critical or high tier. The project must appear as "delay only, no active harm."
Pass criterion: Pre-operational status correctly terminates severity propagation.

Mitigation Propagation Test:
Build a chain where one edge has mitigation_available=true and a BACKUP_FOR edge.
All entities downstream of that edge must be flagged as mitigated.
Pass criterion: Correct mitigation flag propagation.

Depth Boundary Test:
In a 6-hop chain, run impact_propagate with max_depth=3.
Pass criterion: Exact depth boundary enforced. Entities at hops 4-6 absent.
Entities at hops 1-3 complete.

Cycle Safety Test:
Introduce cycle A->B->C->A. Run propagation from a node that reaches A.
Pass criterion: Traversal terminates. Each node appears at most once. No infinite loop.

Combined Scenario Test:
Run impact_scenario_model for two locations simultaneously.
Pass criterion: Shared downstream entities appear exactly once.
Total affected count is less than or equal to sum of individual counts.

### 9.3 Agent Integration Tests

Run each query as natural language through the full agent stack.
Verify tool selection, chaining, and output quality.

Query 1: "Location Alpha is unavailable. Full impact assessment."
Expected: calls impact_propagate. Returns tiered assessment.
Situation report format matches Part 6 structure.

Query 2: "System ARGUS is going down for maintenance Sunday. Who is affected?"
Expected: calls ontology_lookup to identify ARGUS, then impact_reverse_query.

Query 3: "Which of our locations, if disrupted, would hurt us most?"
Expected: calls impact_compare_locations. Returns ranked comparison with reasoning.

Query 4: "Location Alpha is down and Project ATLAS is critical. What are our options?"
Expected: calls impact_propagate then impact_find_mitigations for ATLAS.
Returns specific actionable options -- not generic advice.

Query 5: "Has something like this happened before with Location Alpha?"
Expected: calls impact_historical_context. Returns matching incidents or explicit
"no closely matching incidents found." Never fabricates a precedent.

Query 6: "Hypothetically, if both Alpha and Beta were down simultaneously, what is the impact?"
Expected: calls impact_scenario_model. Output clearly labeled SIMULATION.

Failure Mode -- Unknown Location:
Query: "Location ZETA is compromised."
ZETA does not exist in the graph.
Pass criterion: Agent responds "Location ZETA not found", suggests closest matching
location names, asks for clarification. Does not hallucinate impact data.

Failure Mode -- Degraded Mode:
Neo4j is unavailable. Run Query 1.
Pass criterion: Agent returns graceful degraded response. Attempts partial result
from Elasticsearch. Does not throw unhandled error or return blank response.

Hallucination Test:
Run Query 1 for a location with sparse dependency data.
Pass criterion: Agent reports low confidence due to incomplete data.
Every entity named in the response exists in the graph.
No plausible-sounding fabricated entities.

### 9.4 Performance Tests

Single Propagation Under Load:
50 concurrent impact_propagate requests against 200 locations, 1,000 entities, 3,000 edges.
Pass criterion: p95 latency < 3 seconds. Zero timeout failures.

Mixed Concurrent Workload:
20 impact_propagate + 30 ontology_lookup + 10 impact_compare_locations simultaneously.
Pass criterion: p95 < 3s for propagate. p95 < 300ms for lookup. No resource starvation.

Large Graph Traversal:
Single impact_propagate on the highest-degree location with max_depth=5.
Pass criterion: Completes under 10 seconds. Result complete and correctly ordered.

### 9.5 Ongoing Data Quality Metrics

Compute and prominently display after every ingestion run:

Coverage score: percentage of locations with fully resolved dependency graphs.
This is the most important ongoing quality metric.
Low coverage means low-confidence impact assessments.
Target: above 85% before the system is used in operational conditions.

Resolution rate: percentage of extracted entities that matched existing ontology nodes.
Low resolution rate means the ontology needs enrichment before impact data is valuable.

Review queue burn rate: items resolved per day divided by new items per day.
Must be above 1.0 or the review backlog grows indefinitely.

Historical match rate: percentage of impact queries that returned at least one
relevant historical incident. Proxy for historical file ingestion completeness.

Agent feedback score: ratio of positive to negative feedback on impact_* tool calls,
tracked in LangFuse using the same feedback loop as existing ontology tools.

Display all five on the Impact Dashboard as the health indicators of the impact system.

---

## PART 10 -- DESIGN CONSTRAINTS

The impact graph is not a separate store. Every entity in the impact domain is also
a Concept node in the existing ontology. No parallel node sets, no duplicated graphs.

Pre-operational entities must never elevate downstream severity. A PLANNED project
experiences a delay, not a harm. Its clients are unaffected. This logic must be encoded
explicitly in the propagation engine -- it is not a display concern.

No row from the Excel file is ever silently discarded. Every row produces either
a committed result or a Review Queue item. Silent discards produce false coverage scores.

Propagation queries are bounded at the database level, not application level.
Unbounded graph traversal on a large organizational graph is both a performance
and a correctness risk. Max depth is enforced in Cypher.

The situation report always names specific entities. A summary that says "several
critical projects are affected" without naming them is a quality failure.
Every entity named in the report must exist in the graph -- no paraphrasing,
no gap-filling with plausible fabrications.

is_single_point_of_failure and downstream_count are recomputed after every dependency
graph change. These are operational metrics that decision-makers rely on.
Stale values are dangerous.

Historical incidents are immutable after ingestion. Agents cannot create, modify,
or delete historical incident records. The only write path is the ingestion pipeline
with human review. This preserves the integrity of institutional memory.
