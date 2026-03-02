# Agency Ontology System

> **Organizational Semantic Knowledge Graph for Military-Operational Hebrew**  
> An enterprise-grade, on-premises system that maps military concepts, acronyms, units, systems, and regulations into a structured graph — grounding AI agents in institutional knowledge.

---

## Project Structure

```
agency-ontology/
├── apps/
│   └── portal/            ← Next.js knowledge management UI (TypeScript)
│       ├── app/           ← Page routes (Dashboard, Explore, Review, ...)
│       ├── components/    ← React components (Graph, Layout)
│       ├── next.config.js
│       ├── tailwind.config.ts
│       └── package.json   ← Portal TS dependencies
│
├── packages/
│   ├── shared-types/      ← Zod schemas (TypeScript) — single source of truth
│   │   ├── ontology.ts
│   │   └── package.json
│   └── mcp-tools/ontology/← MCP tool definitions for AI agents (TypeScript)
│       ├── index.ts
│       ├── package.json
│       └── tsconfig.json
│
├── services/              ← Python backend microservices
│   ├── pipeline/          ← Kafka consumers (ingestion, extraction, commit)
│   │   ├── connectors/    ← PDF, OpenMetadata source connectors
│   │   ├── kafka/         ← Client, topic definitions
│   │   ├── models/        ← Pydantic v2 models (ontology.py)
│   │   ├── processors/    ← PDF processor, LLM extractor
│   │   └── resolution/    ← Entity resolver
│   └── retrieval_api/     ← FastAPI (5 endpoints: lookup, search, enrich, schema-context, feedback)
│       ├── routers/
│       ├── services/      ← Neo4j, Elasticsearch, Redis, circuit breaker, embedding
│       └── main.py
│
├── infra/                 ← Docker Compose + all config
│   ├── docker-compose.yml
│   ├── elasticsearch/     ← Index mappings (Hebrew analyzer)
│   ├── grafana/           ← Dashboard JSON + provisioning
│   ├── kafka/             ← Topic init script
│   ├── neo4j/             ← Cypher init constraints
│   ├── otel/              ← OpenTelemetry collector
│   ├── postgres/          ← Init SQL
│   └── prometheus/        ← Scrape config
│
├── tests/
│   ├── backend/           ← pytest (Python)
│   ├── e2e/               ← Playwright (portal smoke tests)
│   ├── evaluation/        ← LangFuse LLM-as-judge + eval_dataset.json
│   └── load/              ← k6 load testing
│
├── docs/
│   └── idf-alias-and-names.pdf   ← Example source document
│
├── package.json           ← Root npm workspace (ties portal + packages)
├── tsconfig.json          ← Root TypeScript config
├── requirements.txt       ← Python backend dependencies
├── pytest.ini             ← pytest configuration
├── vitest.config.ts       ← Vitest configuration
└── playwright.config.ts   ← Playwright E2E configuration
```

### Python vs TypeScript separation

| Layer | Language | Location |
|---|---|---|
| Ingestion pipeline | Python (Kafka, Pydantic, LangChain) | `services/pipeline/` |
| Retrieval API | Python (FastAPI, Neo4j, ES) | `services/retrieval_api/` |
| Agent tools (MCP) | TypeScript (Zod) | `packages/mcp-tools/` |
| Type contracts | TypeScript (Zod) | `packages/shared-types/` |
| Knowledge portal UI | TypeScript (Next.js, React Flow) | `apps/portal/` |
| Infrastructure | YAML/JSON | `infra/` |
| Tests | Python (pytest) + TS (Playwright) | `tests/` |

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker & Docker Compose | v2.x | All infrastructure |
| Python | 3.11+ | Backend microservices |
| Node.js | 20+ | Portal UI + TS tools |
| npm | 10+ | Workspace management |

---

## Getting Started

### 1. Start Infrastructure

```bash
# Start all backend services (Kafka, Neo4j, ES, Redis, Postgres, Mongo, observability)
docker compose -f infra/docker-compose.yml up -d

# Wait ~60 seconds then verify health
docker compose -f infra/docker-compose.yml ps
```

### 2. Install Dependencies

```bash
# Python
pip install -r requirements.txt

# TypeScript (installs all workspaces from root)
npm install
```

### 3. Start the Portal UI

```bash
# Dev server on http://localhost:3000
npm run dev
```

### 4. Start the Retrieval API

```bash
cd services/retrieval_api
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Running the Ingestion Pipeline

### Ingest a PDF

```bash
# From project root
python tests/run_pdf_pipeline.py
# Edit the pdf_path variable inside the script to point to your file
```

To run against the included test document:
```bash
python -c "
import asyncio
from tests.run_pdf_pipeline import run_pipeline_on_pdf
asyncio.run(run_pipeline_on_pdf('docs/idf-alias-and-names.pdf'))
"
```

### Start the Full Kafka Workers

```bash
# Source scan worker
python -m services.pipeline.workers.scan_worker

# LLM extraction worker
python -m services.pipeline.workers.extract_worker

# Graph commit worker
python -m services.pipeline.workers.commit_worker
```

---

## Testing

### Backend Unit Tests (pytest)

```bash
# All backend tests
python -m pytest tests/backend/ -v

# Specific test file
python -m pytest tests/backend/test_entity_resolver.py -v
```

Expect: **6/6 passing** (Hebrew normalization, nikud stripping, geresh removal, fuzzy matching).

### Frontend E2E Tests (Playwright)

```bash
# Install browsers first (once)
npx playwright install chromium

# Run all portal smoke tests (requires portal dev server running)
npm run test:e2e

# Or with the portal auto-started:
npx playwright test
```

### Load Testing (k6)

```bash
# Requires k6 installed: https://k6.io/docs/getting-started/installation
# Requires retrieval API running on :8000
k6 run tests/load/k6_script.js

# Threshold: 95th percentile < 500ms
```

### LangFuse Evaluation (LLM-as-Judge)

```bash
# Set your LangFuse credentials
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=http://localhost:3000  # or your LangFuse instance

# Run evaluation against dataset
python tests/evaluation/evaluate_extraction.py
```

The evaluation script scores each extraction on:
- **Factual Accuracy** (1-5): Is the extraction grounded in the source text?
- **Hebrew Compliance** (1-5): Are terms in formal military Hebrew, acronyms properly handled?

Results appear in LangFuse traces at `http://localhost:3000`.

---

## Evaluation Dataset

Located at `tests/evaluation/eval_dataset.json`.

**Ingestion test cases (7):**

| ID | What it tests |
|---|---|
| ING-001 | Basic role/unit abbreviation resolution (`קמ"ן`) |
| ING-002 | Acronym disambiguation with conflict detection (`שח"ר`) |
| ING-003 | Sensitivity classification (SECRET codename) |
| ING-004 | System → C4I chain + data asset mapping |
| ING-005 | Regulation → System governance relation |
| ING-006 | Data asset table mapping (`idf.order_of_battle` → `סד"כ`) |
| ING-007 | Nikud (diacritics) stripping for term normalization |

**Context enrichment / retrieval test cases (5):**

| ID | What it tests |
|---|---|
| ENR-001 | Agent disambiguation of abbreviation before answering |
| ENR-002 | TextToSQL — returns correct table names for a Hebrew business question |
| ENR-003 | Lookup fallback — unknown acronym returns closest candidates |
| ENR-004 | Sensitivity filter — SECRET concepts blocked without clearance |
| ENR-005 | Multi-hop graph traversal (role → unit → data asset, 2 hops) |

---

## Impact Analysis Extension (v2+)

The Agency Ontology System includes a state-of-the-art **Impact Analysis and Consequence Mapping Engine**. This allows AI agents and operators to simulate disruptions (e.g., a data center outage) and map the cascading downstream effects across the organizational architecture using a canonical **Five-Layer Impact Stack**:
1. **Trigger:** The physical/logical location or entity affected natively.
2. **Direct Consequence:** Departments or business units hosted there.
3. **Operational Entity:** Projects or systems run by those departments.
4. **Stakeholder Consequence:** Clients or end-users served by the projects.
5. **Systemic Implication:** SLI/SLA breaches, PR impact, etc.

### Core Features:
- **Pre-operational Halt (PLANNED status):** Entities marked as `PLANNED` or `SUSPENDED` implicitly halt the propagation of active severity, escalating delays instead of critical outages.
- **Excel Dependency Ingestion:** Safe LLM-assisted connector (`ExcelConnector`) that performs schema detection from unstructured spreadsheets, requires operator confirmation, and routes unparseable data to a Review Queue (zero silent discards).
- **Situation Reports (MCP Native):** Strictly formatted, LLM-generated incident action plans exposing *Critical*, *High*, and *Monitor* tiers based on dependency traversal.
- **Next.js Portal Views:** 5 dedicated visual pages for exploring the dependency graph, reviewing pipeline coverage, assessing location SPOFs (Single Points of Failure), and running impact query scenarios.

## API Endpoints (Retrieval & Impact API)

### Core Ontology Retrieval
| Endpoint | Method | Use case |
|---|---|---|
| `/api/v1/retrieval/lookup/{term}` | GET | Look up a specific Hebrew/English term |
| `/api/v1/retrieval/search` | POST | Hybrid semantic + lexical search |
| `/api/v1/retrieval/enrich` | POST | Extract concepts from a text block for agent grounding |
| `/api/v1/retrieval/schema-context` | POST | Get DB tables/columns for TextToSQL |
| `/api/v1/retrieval/feedback` | POST | Submit agent feedback on an ontology entry |

### Impact Analysis Engine (MCP Target)
| Endpoint | Method | Use case |
|---|---|---|
| `/api/v1/impact/propagate` | POST | Run a Five-Layer impact simulation / extract situation report |
| `/api/v1/impact/reverse` | POST | Find upstream dependencies (who relies on this?) |
| `/api/v1/impact/compare` | POST | Blast-radius comparative analysis between multiple targets |
| `/api/v1/impact/mitigations` | POST | Retrieve explicitly mapped backup strategies and fallback routes |
| `/api/v1/impact/historical` | POST | Fetch historical post-mortems for impacted sectors |
| `/api/v1/impact/coverage` | GET | Check ontology graph density and Single-Point-of-Failure mapping |
| `/api/v1/impact/excel/detect-schema` | POST | Analyze Excel header formats to propose column ingestion mapping |
| `/api/v1/impact/excel/ingest` | POST | Commit Excel-based dependency definitions to the Neo4j graph |

| Health / Metrics | Method | Use case |
|---|---|---|
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

---

## Observability

| Service | URL | Purpose |
|---|---|---|
| Grafana | http://localhost:3001 | Dashboards (pipeline health, API perf) |
| Jaeger | http://localhost:16686 | Distributed traces |
| LangFuse | http://localhost:3000 | LLM call traces + evaluation scores |
| Kafka UI | http://localhost:8080 | Topic browser, consumer lag |
| Prometheus | http://localhost:9090 | Metrics raw |

---

## Phase Completion Status

| Phase | Description | Status |
|---|---|---|
| 1 | Infrastructure + Data Models | ✅ Complete |
| 2 | Kafka Pipeline Core | ✅ Complete |
| 3 | LLM Extraction Pipeline | ✅ Complete |
| 4 | FastAPI Retrieval Services | ✅ Complete |
| 5 | MCP Tools + TypeScript Types | ✅ Complete |
| 6 | Next.js Portal Core Pages | ✅ Complete |
| 7 | Portal Impact Views (5 modules) | ✅ Complete |
| 8 | Impact Analysis Component (Phase 1-8) | ✅ Complete |
| 9 | Observability + Tests | ✅ Complete |

---

## Notes for Developers

- **Hebrew is primary**: All LLM prompts, Elasticsearch field boosting, and UI are Hebrew-first.
- **Sensitivity levels**: `PUBLIC / INTERNAL / CONFIDENTIAL / SECRET` — enforce these in your queries.
- **Nikud stripping**: The entity resolver strips all Hebrew diacritics before fuzzy matching. Test with and without nikud.
- **Abbreviations**: Military Hebrew uses `"` gershayim inside acronyms (e.g., `קמ"ן`). The resolver strips these for normalization.
- **Circuit breaker**: If Neo4j is unavailable, the lookup endpoint gracefully falls back to Elasticsearch (degraded mode).
