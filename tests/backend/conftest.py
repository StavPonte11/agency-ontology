import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_neo4j():
    """Returns a mock for the Async Neo4j Service."""
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock

@pytest.fixture
def mock_es():
    """Returns a mock for the Async Elasticsearch Service."""
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock

@pytest.fixture
def mock_cache():
    """Returns a mock for the Redis Cache Service."""
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock

@pytest.fixture
def mock_embedding():
    """Returns a mock for the Embedding Service."""
    mock = AsyncMock()
    mock.embed.return_value = [0.1] * 1024
    return mock
