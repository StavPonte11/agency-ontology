"""
Redis cache service — TTL-based caching for concept lookups and embeddings.
Also provides distributed locking for pipeline coordination.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_LOOKUP_TTL = 300    # 5 minutes for concept lookups
DEFAULT_EMBEDDING_TTL = 3600 * 24 * 7  # 7 days for embedding cache


class CacheService:
    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(self._url, decode_responses=False)
        await self._redis.ping()
        logger.info(f"Redis connected: {self._url}")

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()

    async def ping(self) -> bool:
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def get(self, key: str) -> Optional[Any]:
        try:
            raw = await self._redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning(f"Cache GET failed for key={key}: {exc}")
            return None

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_LOOKUP_TTL) -> None:
        try:
            await self._redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        except Exception as exc:
            logger.warning(f"Cache SET failed for key={key}: {exc}")

    async def delete(self, key: str) -> None:
        try:
            await self._redis.delete(key)
        except Exception:
            pass

    def lookup_key(self, term: str, max_hops: int = 2) -> str:
        """Cache key for concept lookup."""
        return f"ontology:lookup:{term.lower().strip()}:{max_hops}"

    def embedding_key(self, text_hash: str, model: str) -> str:
        """Cache key for computed embedding."""
        return f"ontology:emb:{model}:{text_hash}"

    async def get_embedding(
        self, text_hash: str, model: str
    ) -> Optional[list[float]]:
        """Retrieve a cached embedding vector."""
        key = self.embedding_key(text_hash, model)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            import struct
            vals = struct.unpack(f"{len(raw) // 4}f", raw)
            return list(vals)
        except Exception:
            return None

    async def set_embedding(
        self, text_hash: str, model: str, embedding: list[float]
    ) -> None:
        """Cache an embedding vector as packed binary floats."""
        key = self.embedding_key(text_hash, model)
        try:
            import struct
            packed = struct.pack(f"{len(embedding)}f", *embedding)
            await self._redis.setex(key, DEFAULT_EMBEDDING_TTL, packed)
        except Exception as exc:
            logger.warning(f"Embedding cache SET failed: {exc}")
