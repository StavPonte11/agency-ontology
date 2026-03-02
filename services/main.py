"""
Agency Ontology Retrieval API — FastAPI application.
Agent-facing service: lookup, search, enrich, schema-context, feedback.
Hebrew-first: all lookup supports Hebrew queries.

Usage:
    # From project root:
    uvicorn services.retrieval_api.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
# ── Router imports (absolute, works with uvicorn module path) ──────────────────
from services.retrieval_api.routers import (
    lookup,
    search,
    enrich,
    schema_context,
    feedback,
    impact,
)
from services.retrieval_api.services.impact_service import ImpactService
from services.retrieval_api.services.cache_service import CacheService
from services.retrieval_api.services.circuit_breaker import CircuitBreakerRegistry
from services.retrieval_api.services.circuit_breaker import EmbeddingService
from services.retrieval_api.services.elasticsearch_service import ElasticsearchService
from services.retrieval_api.services.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all service connections on startup, close on shutdown."""
    logger.info("Starting Agency Ontology Retrieval API...")

    app.state.neo4j = Neo4jService(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    try:
        await app.state.neo4j.connect()
    except Exception as exc:
        logger.warning("Neo4j unavailable on startup (degraded mode): %s", exc)

    app.state.es = ElasticsearchService(url=settings.elasticsearch_url)
    try:
        await app.state.es.connect()
    except Exception as exc:
        logger.warning("Elasticsearch unavailable on startup (degraded mode): %s", exc)

    app.state.cache = CacheService(redis_url=settings.redis_url)
    try:
        await app.state.cache.connect()
    except Exception as exc:
        logger.warning("Redis unavailable on startup (degraded mode): %s", exc)

    app.state.embedding = EmbeddingService(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
    )

    app.state.circuit_breakers = CircuitBreakerRegistry(
        services={
            "neo4j": {"threshold": 5, "reset_timeout": 120},
            "openai": {"threshold": 5, "reset_timeout": 60},
            "elasticsearch": {"threshold": 5, "reset_timeout": 60},
        }
    )

    # Impact Analysis Service
    try:
        app.state.impact = await ImpactService.create(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        logger.info("ImpactService initialized — impact analysis active.")
    except Exception as exc:
        app.state.impact = None
        logger.warning("ImpactService unavailable on startup (degraded mode): %s", exc)

    logger.info("All services connected — API ready.")
    yield

    # Shutdown
    await app.state.neo4j.close()
    await app.state.es.close()
    await app.state.cache.close()
    if app.state.impact:
        await app.state.impact.close()
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
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def otel_middleware(request: Request, call_next):
    """OpenTelemetry span injection."""
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("agency-ontology-retrieval")
        with tracer.start_as_current_span(f"{request.method} {request.url.path}"):
            return await call_next(request)
    except Exception:
        return await call_next(request)


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(lookup.router, prefix="/v1", tags=["lookup"])
app.include_router(search.router, prefix="/v1", tags=["search"])
app.include_router(enrich.router, prefix="/v1", tags=["enrich"])
app.include_router(schema_context.router, prefix="/v1", tags=["schema-context"])
app.include_router(feedback.router, prefix="/v1", tags=["feedback"])
app.include_router(impact.router, prefix="/v1", tags=["impact"])


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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
