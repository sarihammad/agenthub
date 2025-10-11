"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Dict

import pytest
import redis.asyncio as aioredis
from fastapi.testclient import TestClient

from agenthub.app import create_app
from agenthub.auth.api_keys import create_api_key
from agenthub.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Redis client fixture."""
    client = await aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,
    )
    yield client
    await client.flushdb()
    await client.close()


@pytest.fixture
async def admin_api_key(redis_client: aioredis.Redis) -> Dict[str, str]:
    """Create an admin API key."""
    return await create_api_key(redis_client, "admin", "test_admin")


@pytest.fixture
async def client_api_key(redis_client: aioredis.Redis) -> Dict[str, str]:
    """Create a client API key."""
    return await create_api_key(redis_client, "client", "test_client")


@pytest.fixture
def app() -> TestClient:
    """FastAPI test client."""
    return TestClient(create_app())


@pytest.fixture
def admin_headers(admin_api_key: Dict[str, str]) -> Dict[str, str]:
    """Admin authorization headers."""
    return {"Authorization": f"Bearer {admin_api_key['api_key']}"}


@pytest.fixture
def client_headers(client_api_key: Dict[str, str]) -> Dict[str, str]:
    """Client authorization headers."""
    return {"Authorization": f"Bearer {client_api_key['api_key']}"}

