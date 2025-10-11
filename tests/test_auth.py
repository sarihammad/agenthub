"""Test authentication and RBAC."""

import pytest
import redis.asyncio as aioredis

from agenthub.auth.api_keys import create_api_key, revoke_api_key, validate_api_key


@pytest.mark.asyncio
async def test_create_api_key(redis_client: aioredis.Redis) -> None:
    """Test API key creation."""
    key_info = await create_api_key(redis_client, "client", "test_key")

    assert "key_id" in key_info
    assert "api_key" in key_info
    assert key_info["role"] == "client"
    assert "." in key_info["api_key"]


@pytest.mark.asyncio
async def test_validate_api_key(redis_client: aioredis.Redis) -> None:
    """Test API key validation."""
    key_info = await create_api_key(redis_client, "developer")

    # Valid key
    validated = await validate_api_key(redis_client, key_info["api_key"])
    assert validated is not None
    assert validated["role"] == "developer"

    # Invalid key
    invalid = await validate_api_key(redis_client, "invalid.key")
    assert invalid is None


@pytest.mark.asyncio
async def test_revoke_api_key(redis_client: aioredis.Redis) -> None:
    """Test API key revocation."""
    key_info = await create_api_key(redis_client, "client")

    # Revoke
    result = await revoke_api_key(redis_client, key_info["key_id"])
    assert result is True

    # Validate after revocation
    validated = await validate_api_key(redis_client, key_info["api_key"])
    assert validated is None


def test_admin_endpoint_requires_admin(app, client_headers) -> None:  # type: ignore
    """Test that admin endpoints require admin role."""
    response = app.post(
        "/v1/admin/api-keys",
        json={"role": "client"},
        headers=client_headers,
    )
    assert response.status_code == 403


def test_missing_authorization_header(app) -> None:  # type: ignore
    """Test that missing auth header returns 401."""
    response = app.get("/v1/tools")
    assert response.status_code == 401

