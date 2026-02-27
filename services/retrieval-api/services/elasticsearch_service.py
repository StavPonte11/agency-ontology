"""
Elasticsearch service — hybrid RRF search (BM25 + kNN) for Agency Ontology.
Implements ES 8.12+ retriever.rrf for combined lexical + semantic search.

Hebrew military domain:
- Uses hebrew_military analyzer for Hebrew text fields
- Returns Hebrew names when available
- kNN filters applied inside knn block (ES POST-filter behavior)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from elasticsearch import AsyncElasticsearch

logger = logging.getLogger(__name__)

CONCEPTS_INDEX = "agency-ontology-concepts"
CHUNKS_INDEX = "agency-ontology-chunks"


class ElasticsearchService:
    """Async Elasticsearch service — concept search and index management."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._es: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        self._es = AsyncElasticsearch([self._url], request_timeout=30)
        info = await self._es.info()
        logger.info(f"Elasticsearch connected: {info['version']['number']}")
        await self._ensure_indexes()

    async def close(self) -> None:
        if self._es:
            await self._es.close()

    async def ping(self) -> bool:
        try:
            return await self._es.ping()
        except Exception:
            return False

    async def _ensure_indexes(self) -> None:
        """Create indexes with mappings if they don't exist."""
        import json
        import os

        for index_name, mapping_file in [
            (CONCEPTS_INDEX, "concepts_mapping.json"),
            (CHUNKS_INDEX, "chunks_mapping.json"),
        ]:
            if not await self._es.indices.exists(index=index_name):
                mapping_path = os.path.join(
                    os.path.dirname(__file__),
                    "../../../../infra/elasticsearch",
                    mapping_file,
                )
                try:
                    with open(mapping_path) as f:
                        mapping = json.load(f)
                    await self._es.indices.create(index=index_name, body=mapping)
                    logger.info(f"Created Elasticsearch index: {index_name}")
                except FileNotFoundError:
                    logger.warning(f"Mapping file not found: {mapping_path}")

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        filters: dict[str, Any],
        k: int = 20,
        search_mode: str = "hybrid",
    ) -> list[dict[str, Any]]:
        """
        RRF hybrid search: BM25 + kNN combined with Reciprocal Rank Fusion (ES 8.12+).

        CRITICAL: kNN filters are POST-filters in ES.
        Always apply filters inside the knn block.
        num_candidates = max(100, k * 10) to avoid 0-result edge cases.
        """
        num_candidates = max(100, k * 10)

        # Build filter clauses
        filter_clauses = self._build_filter_clauses(filters)

        if search_mode == "lexical":
            return await self._lexical_search(query_text, filter_clauses, k)
        elif search_mode == "semantic":
            return await self._knn_search(query_embedding, filter_clauses, k, num_candidates)
        else:
            return await self._rrf_hybrid_search(
                query_text, query_embedding, filter_clauses, k, num_candidates
            )

    def _build_filter_clauses(self, filters: dict[str, Any]) -> list[dict]:
        clauses = []
        if filters.get("concept_types"):
            clauses.append({"terms": {"concept_type": filters["concept_types"]}})
        if filters.get("domains"):
            clauses.append({"terms": {"domain": filters["domains"]}})
        if filters.get("status"):
            clauses.append({"terms": {"status": filters["status"]}})
        if filters.get("confidence_min") is not None:
            clauses.append({"range": {"confidence": {"gte": filters["confidence_min"]}}})
        # Default: never return DEPRECATED unless explicitly requested
        if "DEPRECATED" not in (filters.get("status") or []):
            clauses.append({"term": {"status": {"value": "DEPRECATED"}}})
            # Rewrite: exclude DEPRECATED
            clauses = [c for c in clauses if c != {"term": {"status": {"value": "DEPRECATED"}}}]
            clauses.append({"bool": {"must_not": [{"term": {"status": "DEPRECATED"}}]}})
        return clauses

    async def _rrf_hybrid_search(
        self,
        query_text: str,
        query_embedding: list[float],
        filter_clauses: list[dict],
        k: int,
        num_candidates: int,
    ) -> list[dict[str, Any]]:
        """ES 8.12+ RRF retriever — native BM25 + kNN fusion."""
        body = {
            "size": k,
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {
                            "standard": {
                                "query": {
                                    "bool": {
                                        "should": [
                                            # Hebrew name gets highest boost
                                            {"match": {"name_he": {"query": query_text, "boost": 4.0}}},
                                            # English name
                                            {"match": {"name": {"query": query_text, "boost": 3.0}}},
                                            # Aliases
                                            {"match": {"aliases": {"query": query_text, "boost": 2.0}}},
                                            # Description
                                            {"match": {"description": {"query": query_text, "boost": 1.0}}},
                                            {"match": {"description_he": {"query": query_text, "boost": 1.0}}},
                                        ],
                                        "filter": filter_clauses,
                                    }
                                }
                            }
                        },
                        {
                            "knn": {
                                "field": "embedding",
                                "query_vector": query_embedding,
                                "num_candidates": num_candidates,
                                "k": k,
                                "filter": filter_clauses,  # POST-filter for kNN
                            }
                        },
                    ],
                    "rank_constant": 20,
                    "rank_window_size": k * 2,
                }
            },
        }
        response = await self._es.search(index=CONCEPTS_INDEX, body=body)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def _lexical_search(
        self, query_text: str, filter_clauses: list[dict], k: int
    ) -> list[dict[str, Any]]:
        body = {
            "size": k,
            "query": {
                "bool": {
                    "should": [
                        {"match": {"name_he": {"query": query_text, "boost": 4.0}}},
                        {"match": {"name": {"query": query_text, "boost": 3.0}}},
                        {"match": {"aliases": {"query": query_text, "boost": 2.0}}},
                        {"match": {"description": {"query": query_text}}},
                        {"match": {"description_he": {"query": query_text}}},
                    ],
                    "filter": filter_clauses,
                }
            },
        }
        response = await self._es.search(index=CONCEPTS_INDEX, body=body)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def _knn_search(
        self,
        query_embedding: list[float],
        filter_clauses: list[dict],
        k: int,
        num_candidates: int,
    ) -> list[dict[str, Any]]:
        body = {
            "size": k,
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "num_candidates": num_candidates,
                "k": k,
                "filter": filter_clauses,
            },
        }
        response = await self._es.search(index=CONCEPTS_INDEX, body=body)
        return [hit["_source"] for hit in response["hits"]["hits"]]

    async def index_concept(self, doc: dict[str, Any]) -> None:
        """Index or update a concept document."""
        concept_id = doc["concept_id"]
        await self._es.index(index=CONCEPTS_INDEX, id=concept_id, document=doc)

    async def delete_concept(self, concept_id: str) -> None:
        await self._es.delete(index=CONCEPTS_INDEX, id=concept_id, ignore=[404])

    async def index_chunk(self, doc: dict[str, Any]) -> None:
        await self._es.index(index=CHUNKS_INDEX, id=doc["chunk_id"], document=doc)
