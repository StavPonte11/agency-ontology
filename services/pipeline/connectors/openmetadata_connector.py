"""
OpenMetadata connector — Agency Ontology Pipeline
Ingests table/column metadata and glossary terms from OpenMetadata.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import httpx
from pydantic import BaseModel, Field

from .base import ConnectorHealthStatus, ConnectorType, SourceConnector, SourceDocument

logger = logging.getLogger(__name__)


class OpenMetadataConfig(BaseModel):
    base_url: str = Field(description="OpenMetadata API base URL, e.g. http://openmetadata:8585/api")
    api_token: str = Field(description="OpenMetadata API bearer token")
    include_glossaries: bool = Field(default=True)
    include_tables: bool = Field(default=True)
    include_columns: bool = Field(default=True)
    include_lineage: bool = Field(default=True)
    page_size: int = Field(default=50, ge=1, le=200)
    rate_limit_rpm: int = Field(default=100)
    custom_api_url: Optional[str] = None
    custom_api_token: Optional[str] = None


class OpenMetadataConnector(SourceConnector):
    connector_type = ConnectorType.OPENMETADATA

    def __init__(self, config: OpenMetadataConfig, connector_id: str) -> None:
        self._config = config
        self._connector_id = connector_id
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={"Authorization": f"Bearer {config.api_token}"},
            timeout=30.0,
        )
        self._request_interval = 60.0 / config.rate_limit_rpm

    def validate_config(self, config: dict[str, Any]) -> bool:
        OpenMetadataConfig(**config)
        return True

    async def test_connection(self) -> ConnectorHealthStatus:
        import time
        start = time.monotonic()
        try:
            resp = await self._client.get("/v1/system/status")
            resp.raise_for_status()
            return ConnectorHealthStatus(healthy=True, latency_ms=(time.monotonic() - start) * 1000)
        except Exception as exc:
            return ConnectorHealthStatus(healthy=False, error=str(exc))

    async def list_documents(self, since: Optional[datetime] = None) -> AsyncIterator[SourceDocument]:
        if self._config.include_tables:
            async for doc in self._paginate_tables(since):
                yield doc
        if self._config.include_glossaries:
            async for doc in self._paginate_glossary_terms(since):
                yield doc

    async def _paginate_tables(self, since: Optional[datetime]) -> AsyncIterator[SourceDocument]:
        after: Optional[str] = None
        fields = "columns,tags,owners"
        if self._config.include_lineage:
            fields += ",lineage"

        while True:
            params: dict[str, Any] = {"limit": self._config.page_size, "fields": fields}
            if after:
                params["after"] = after
            if since:
                params["updatedAfter"] = int(since.timestamp() * 1000)

            await asyncio.sleep(self._request_interval)
            try:
                resp = await self._client.get("/v1/tables", params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error(f"OpenMetadata tables API error: {exc}")
                break

            for table in data.get("data", []):
                try:
                    content = self._build_table_document(table)
                    yield SourceDocument(
                        external_id=table["id"],
                        title=table.get("fullyQualifiedName", table["name"]),
                        content_type="structured_catalog",
                        raw_content=content,
                        metadata={
                            "service": table.get("service", {}).get("name"),
                            "database": table.get("database", {}).get("name"),
                            "schema": table.get("databaseSchema", {}).get("name"),
                            "tier": table.get("tier", {}).get("tagFQN"),
                            "owner": table.get("owner", {}).get("name"),
                        },
                        content_hash=SourceDocument.compute_hash(content),
                        document_type="CATALOG",
                        source_connector_id=self._connector_id,
                        connector_type=ConnectorType.OPENMETADATA,
                        primary_language="en",  # OpenMetadata metadata is typically English
                    )
                except Exception as exc:
                    logger.warning(f"Failed to process table {table.get('id')}: {exc}")
                    continue

            after = data.get("paging", {}).get("after")
            if not after:
                break

    def _build_table_document(self, table: dict[str, Any]) -> dict[str, Any]:
        return {
            "table": {
                "id": table["id"],
                "name": table["name"],
                "fqn": table.get("fullyQualifiedName"),
                "description": table.get("description", ""),
                "table_type": table.get("tableType"),
                "tags": [t.get("tagFQN") for t in table.get("tags", [])],
                "owner": table.get("owner", {}).get("name"),
                "tier": table.get("tier", {}).get("tagFQN"),
            },
            "columns": [
                {
                    "name": col["name"],
                    "data_type": col.get("dataType"),
                    "description": col.get("description", ""),
                    "tags": [t.get("tagFQN") for t in col.get("tags", [])],
                    "is_nullable": col.get("constraint") != "NOT_NULL",
                }
                for col in table.get("columns", [])
            ],
            "lineage": table.get("lineage", {}),
        }

    async def _paginate_glossary_terms(self, since: Optional[datetime]) -> AsyncIterator[SourceDocument]:
        after: Optional[str] = None
        while True:
            params: dict[str, Any] = {
                "limit": self._config.page_size,
                "fields": "reviewers,tags,relatedTerms",
            }
            if after:
                params["after"] = after

            await asyncio.sleep(self._request_interval)
            try:
                resp = await self._client.get("/v1/glossaryTerms", params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error(f"OpenMetadata glossary API error: {exc}")
                break

            for term in data.get("data", []):
                content = {
                    "id": term["id"],
                    "name": term["name"],
                    "fqn": term.get("fullyQualifiedName"),
                    "description": term.get("description", ""),
                    "synonyms": term.get("synonyms", []),
                    "related_terms": [r.get("name") for r in term.get("relatedTerms", [])],
                    "tags": [t.get("tagFQN") for t in term.get("tags", [])],
                }
                yield SourceDocument(
                    external_id=term["id"],
                    title=term.get("fullyQualifiedName", term["name"]),
                    content_type="structured_catalog",
                    raw_content=content,
                    metadata={},
                    content_hash=SourceDocument.compute_hash(content),
                    document_type="CATALOG",
                    source_connector_id=self._connector_id,
                    connector_type=ConnectorType.OPENMETADATA,
                    primary_language="en",
                )

            after = data.get("paging", {}).get("after")
            if not after:
                break

    async def get_document(self, external_id: str) -> SourceDocument:
        resp = await self._client.get(
            f"/v1/tables/{external_id}",
            params={"fields": "columns,tags,owners,lineage"},
        )
        resp.raise_for_status()
        data = resp.json()
        content = self._build_table_document(data)
        return SourceDocument(
            external_id=external_id,
            title=data.get("fullyQualifiedName", ""),
            content_type="structured_catalog",
            raw_content=content,
            metadata={},
            content_hash=SourceDocument.compute_hash(content),
            document_type="CATALOG",
            source_connector_id=self._connector_id,
            connector_type=ConnectorType.OPENMETADATA,
            primary_language="en",
        )

    def get_config_schema(self) -> dict[str, Any]:
        return OpenMetadataConfig.model_json_schema()
