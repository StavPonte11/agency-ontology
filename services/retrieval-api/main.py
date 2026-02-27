"""
Agency Ontology Retrieval API — FastAPI application.
Agent-facing service: lookup, search, enrich, schema-context, feedback.
Hebrew-first: all lookup supports Hebrew queries.

Usage:
    # From project root:
    uvicorn services.retrieval_api.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Router imports (absolute, works with uvicorn module path) ──────────────────
from services.retrieval_api.routers import lookup, search, enrich, schema_context, feedback
from services.retrieval_api.services.neo4j_service import Neo4jService
from services.retrieval_api.services.elasticsearch_service import ElasticsearchService
from services.retrieval_api.services.cache_service import CacheService
from services.retrieval_api.services.embedding_service import EmbeddingService
from services.retrieval_api.services.circuit_breaker import CircuitBreakerRegistry

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all service connections on startup, close on shutdown."""
    logger.info("Starting Agency Ontology Retrieval API...")

    app.state.neo4j = Neo4jService(
        uri=os.environ["NEO4J_URI"],
        user=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    await app.state.neo4j.connect()

    app.state.es = ElasticsearchService(
        url=os.environ["ELASTICSEARCH_URL"]
    )
    await app.state.es.connect()

    app.state.cache = CacheService(redis_url=os.environ["REDIS_URL"])
    await app.state.cache.connect()

    app.state.embedding = EmbeddingService(
        base_url=os.environ["OPENAI_BASE_URL"],
        model=os.environ.get("EMBEDDING_MODEL", "mxbai-embed-large"),
    )

    app.state.circuit_breakers = CircuitBreakerRegistry(
        services={
            "neo4j":          {"threshold": 5, "reset_timeout": 120},
            "openai":         {"threshold": 5, "reset_timeout":  60},
            "elasticsearch":  {"threshold": 5, "reset_timeout":  60},
        }
    )

    logger.info("All services connected — API ready.")
    yield

    # Shutdown
    await app.state.neo4j.close()
    await app.state.es.close()
    await app.state.cache.close()
    logger.info("Agency Ontology Retrieval API shut down.")


app = FastAPI(
    title="Agency Ontology Retrieval API",
    description=(
        "Organizational knowledge graph service for The Agency platform. "
        "Provides concept lookup, hybrid search, context enrichment, "
        "database schema context, and feedback endpoints for all agents. "
        "Primary domain: Hebrew military-operational terminology."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def otel_middleware(request: Request, call_next):
    """OpenTelemetry span injection."""
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("agency-ontology-retrieval")
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}"
        ):
            return await call_next(request)
    except Exception:
        return await call_next(request)


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(lookup.router,         prefix="/v1", tags=["lookup"])
app.include_router(search.router,         prefix="/v1", tags=["search"])
app.include_router(enrich.router,         prefix="/v1", tags=["enrich"])
app.include_router(schema_context.router, prefix="/v1", tags=["schema-context"])
app.include_router(feedback.router,       prefix="/v1", tags=["feedback"])


# ── Health endpoints ───────────────────────────────────────────────────────────

@app.get("/health", include_in_schema=False)
async def health(request: Request) -> dict[str, Any]:
    neo4j_ok = await request.app.state.neo4j.ping()
    es_ok = await request.app.state.es.ping()
    cache_ok = await request.app.state.cache.ping()
    ok = neo4j_ok and es_ok and cache_ok
    return {
        "status": "healthy" if ok else "degraded",
        "neo4j": neo4j_ok,
        "elasticsearch": es_ok,
        "cache": cache_ok,
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from fastapi.responses import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        return {"error": "prometheus_client not installed"}
