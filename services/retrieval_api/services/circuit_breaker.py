"""Circuit breaker and embedding service for the retrieval API."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CBState(str, Enum):
    CLOSED = "CLOSED"     # Normal — requests pass through
    OPEN = "OPEN"         # Tripped — requests fail fast
    HALF_OPEN = "HALF_OPEN"  # Testing — allow one probe request


@dataclass
class CircuitBreaker:
    service: str
    threshold: int = 5      # Failures before tripping
    reset_timeout: int = 60 # Seconds before trying HALF_OPEN
    _state: CBState = field(default=CBState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _last_failure: float = field(default=0.0, init=False)

    def allow_request(self) -> bool:
        if self._state == CBState.CLOSED:
            return True
        if self._state == CBState.OPEN:
            if time.monotonic() - self._last_failure > self.reset_timeout:
                self._state = CBState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: allow one probe

    def record_success(self) -> None:
        self._failures = 0
        self._state = CBState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure = time.monotonic()
        if self._failures >= self.threshold:
            if self._state != CBState.OPEN:
                logger.warning(f"Circuit breaker OPEN for {self.service}")
            self._state = CBState.OPEN

    @property
    def is_open(self) -> bool:
        return self._state == CBState.OPEN


class CircuitBreakerRegistry:
    def __init__(self, services: dict[str, dict]) -> None:
        self._breakers = {
            name: CircuitBreaker(service=name, **cfg)
            for name, cfg in services.items()
        }

    def get(self, service: str) -> CircuitBreaker:
        return self._breakers.get(service, CircuitBreaker(service=service))

    def to_metrics(self) -> dict:
        return {
            name: {"state": cb._state.value, "failures": cb._failures}
            for name, cb in self._breakers.items()
        }


class EmbeddingService:
    """Generates text embeddings via OpenAI API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._model = model

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a text string. Hebrew text supported natively."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._api_key)
        response = await client.embeddings.create(model=self._model, input=text)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts — batch for efficiency."""
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=self._api_key)
        response = await client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    def text_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
