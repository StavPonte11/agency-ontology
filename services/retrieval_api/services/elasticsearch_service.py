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
        from pathlib import Path

        # services/retrieval_api/services/ -> up 3 levels -> project root -> infra/elasticsearch
        project_root = Path(__file__).parents[3]
        infra_dir = project_root / "infra" / "elasticsearch"

        for index_name, mapping_file in [
            (CONCEPTS_INDEX, "concepts_mapping.json"),
            (CHUNKS_INDEX, "chunks_mapping.json"),
        ]:
            if not await self._es.indices.exists(index=index_name):
                mapping_path = infra_dir / mapping_file
                try:
                    with open(mapping_path) as f:
                        mapping = json.load(f)
                    await self._es.indices.create(index=index_name, body=mapping)
                    logger.info(f"Created Elasticsearch index: {index_name}")
                except FileNotFoundError:
                    logger.warning(
                        f"Mapping file not found: {mapping_path} — "
                        f"index {index_name} will be auto-created by ES with dynamic mapping"
                    )

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
            return await self._knn_search(
                query_embedding, filter_clauses, k, num_candidates
            )
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
            clauses.append(
                {"range": {"confidence": {"gte": filters["confidence_min"]}}}
            )
        # Default: never return DEPRECATED unless explicitly requested
        if "DEPRECATED" not in (filters.get("status") or []):
            clauses.append({"term": {"status": {"value": "DEPRECATED"}}})
            # Rewrite: exclude DEPRECATED
            clauses = [
                c for c in clauses if c != {"term": {"status": {"value": "DEPRECATED"}}}
            ]
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
                                            {
                                                "match": {
                                                    "name_he": {
                                                        "query": query_text,
                                                        "boost": 4.0,
                                                    }
                                                }
                                            },
                                            # English name
                                            {
                                                "match": {
                                                    "name": {
                                                        "query": query_text,
                                                        "boost": 3.0,
                                                    }
                                                }
                                            },
                                            # Aliases
                                            {
                                                "match": {
                                                    "aliases": {
                                                        "query": query_text,
                                                        "boost": 2.0,
                                                    }
                                                }
                                            },
                                            # Description
                                            {
                                                "match": {
                                                    "description": {
                                                        "query": query_text,
                                                        "boost": 1.0,
                                                    }
                                                }
                                            },
                                            {
                                                "match": {
                                                    "description_he": {
                                                        "query": query_text,
                                                        "boost": 1.0,
                                                    }
                                                }
                                            },
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
        """Index or update a concept document. Hierarchy fields are written through transparently."""
        concept_id = doc["concept_id"]
        await self._es.index(index=CONCEPTS_INDEX, id=concept_id, document=doc)

    async def update_hierarchy_fields(
        self,
        concept_id: str,
        ancestor_ids: list[str],
        ancestor_names: list[str],
        hierarchy_depth: int,
        instance_of: Optional[str] = None,
        subclass_of: Optional[str] = None,
    ) -> None:
        """
        Partial update for hierarchy-specific fields on an existing ES document.
        Called by hierarchy_cache after recomputing the ancestor chain.
        """
        await self._es.update(
            index=CONCEPTS_INDEX,
            id=concept_id,
            body={"doc": {
                "ancestor_ids":    ancestor_ids,
                "ancestor_names":  ancestor_names,
                "hierarchy_depth": hierarchy_depth,
                "instance_of":     instance_of,
                "subclass_of":     subclass_of,
            }}
        )
        logger.debug(f"Hierarchy fields updated in ES for concept={concept_id}: depth={hierarchy_depth}")

    async def search_by_class(
        self,
        class_concept_id: str,
        include_subclasses: bool = True,
        filters: dict[str, Any] | None = None,
        k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Find all concepts that are instances or subclasses of a given class.
        Uses the pre-computed `ancestor_ids` field — O(1) lookup, not live graph traversal.

        Parameters
        ----------
        class_concept_id:
            The ID of the class concept (e.g. the ID for "Territorial Brigade").
        include_subclasses:
            If True, includes both instances and subclasses.
            If False, returns only instances (is_class=False).
        filters:
            Optional additional filters: domains, confidence_min.
        k:
            Maximum results to return.
        """
        filters = filters or {}
        must_clauses = [{"term": {"ancestor_ids": class_concept_id}}]

        if not include_subclasses:
            must_clauses.append({"term": {"is_class": False}})

        filter_clauses = []
        if filters.get("domains"):
            filter_clauses.append({"terms": {"domain": filters["domains"]}})
        if filters.get("confidence_min") is not None:
            filter_clauses.append({"range": {"confidence": {"gte": filters["confidence_min"]}}})

        body = {
            "size": k,
            "query": {
                "bool": {
                    "must":   must_clauses,
                    "filter": filter_clauses,
                }
            },
            "sort": [{"confidence": "desc"}, "_score"],
        }
        try:
            response = await self._es.search(index=CONCEPTS_INDEX, body=body)
            return [hit["_source"] for hit in response["hits"]["hits"]]
        except Exception as exc:
            logger.error(f"search_by_class failed for class={class_concept_id}: {exc}")
            return []

    async def delete_concept(self, concept_id: str) -> None:
        await self._es.delete(index=CONCEPTS_INDEX, id=concept_id, ignore=[404])

    async def index_chunk(self, doc: dict[str, Any]) -> None:
        await self._es.index(index=CHUNKS_INDEX, id=doc["chunk_id"], document=doc)
