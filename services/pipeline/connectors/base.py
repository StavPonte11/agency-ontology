"""
Source connector base interface for the Agency Ontology pipeline.
Implementing a new connector requires ONLY implementing this interface.
The pipeline engine is fully source-agnostic.
"""
from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConnectorType(str, Enum):
    PDF = "PDF"
    OPENMETADATA = "OPENMETADATA"
    CUSTOM_API = "CUSTOM_API"
    CONFLUENCE = "CONFLUENCE"
    GIT = "GIT"
    EXCEL = "EXCEL"



class SourceDocument(BaseModel):
    """
    Strictly typed representation of a document from any source connector.
    This is the canonical input to the pipeline extraction stage.
    """

    external_id: str = Field(description="Unique ID within this connector's scope")
    title: str
    content_type: str = Field(
        description="'pdf' | 'structured_catalog' | 'markdown' | 'code' | 'plaintext'"
    )
    raw_content: bytes | dict[str, Any]  # bytes for binary (PDF), dict for structured
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = Field(description="SHA-256 of raw_content")
    document_type: str  # DocumentType enum value
    source_connector_id: str
    connector_type: ConnectorType
    # Primary language of the document — for military Hebrew content set to "he"
    primary_language: str = Field(default="he", description="Primary language: 'he' | 'en' | 'mixed'")

    @classmethod
    def compute_hash(cls, content: bytes | dict[str, Any]) -> str:
        """Compute deterministic SHA-256 for deduplication."""
        if isinstance(content, bytes):
            data = content
        else:
            data = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    model_config = {"arbitrary_types_allowed": True}


class ConnectorHealthStatus(BaseModel):
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class SourceConnector(ABC):
    """
    Abstract base class for all ontology data source connectors.

    Contract:
    - One connector implementation = one connector type
    - Pipeline workers are completely agnostic to connector type
    - New connectors only need to implement this interface
    """

    connector_type: ConnectorType  # Must be set as class attribute on subclass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> bool:
        """
        Validate connector configuration.
        Raises ValueError with a user-readable message on failure.
        """
        ...

    @abstractmethod
    async def test_connection(self) -> ConnectorHealthStatus:
        """Test source connectivity. Must complete within 10 seconds."""
        ...

    @abstractmethod
    async def list_documents(
        self,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[SourceDocument]:
        """
        Async-yield documents from source.
        - If `since` provided: yield only documents modified after that datetime.
        - MUST be resumable: one document failure must not stop the stream.
        - MUST yield lazily — do not load all documents into memory.
        - Set primary_language="he" for Hebrew military documents.
        """
        ...

    @abstractmethod
    async def get_document(self, external_id: str) -> SourceDocument:
        """Fetch a single document by external ID for targeted re-processing."""
        ...

    @abstractmethod
    def get_config_schema(self) -> dict[str, Any]:
        """
        Return JSON Schema of connector's config shape.
        Used by the UI to auto-generate connector configuration forms.
        """
        ...
