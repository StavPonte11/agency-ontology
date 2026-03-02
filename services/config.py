"""
Application settings — Agency Ontology Retrieval API.
All configuration is loaded from environment variables (or a .env file).
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Retrieval API configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Neo4j ──────────────────────────────────────────────────────────────────
    neo4j_uri: str = Field(..., description="Bolt URI for Neo4j, e.g. bolt://localhost:7687")
    neo4j_user: str = Field(..., description="Neo4j username")
    neo4j_password: str = Field(..., description="Neo4j password")

    # ── Elasticsearch ──────────────────────────────────────────────────────────
    elasticsearch_url: str = Field(..., description="Elasticsearch base URL, e.g. http://localhost:9200")

    # ── Redis / Cache ──────────────────────────────────────────────────────────
    redis_url: str = Field(..., description="Redis connection URL, e.g. redis://localhost:6379/0")

    # ── OpenAI ─────────────────────────────────────────────────────────────────
    openai_api_key: str = Field("", description="OpenAI API key (leave empty when using Ollama)")
    embedding_model: str = Field("text-embedding-3-small", description="Embedding model name")

    # ── LLM / Ollama ───────────────────────────────────────────────────────────
    pipeline_model: str = Field("gpt-oss-120b", description="Model name for LLM extraction")
    ollama_base_url: Optional[str] = Field(
        None,
        description="Ollama base URL (e.g. http://localhost:11434/v1). "
                    "When set, extraction uses Ollama instead of OpenAI.",
    )


# Module-level singleton — import and use `settings` directly.
settings = Settings()
