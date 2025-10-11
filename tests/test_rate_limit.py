"""Test rate limiting."""

import pytest
import redis.asyncio as aioredis

from agenthub.governance.rate_limiter import check_rate_limit


@pytest.mark.asyncio
async def test_rate_limit_allows_within_limit(redis_client: aioredis.Redis) -> None:
    """Test that requests within limit are allowed."""
    api_key_id = "test_key_1"

    for _ in range(5):  # Within QPS limit
        allowed, retry_after = await check_rate_limit(redis_client, api_key_id)
        assert allowed is True
        assert retry_after == 0


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_limit(redis_client: aioredis.Redis) -> None:
    """Test that requests over limit are blocked."""
    api_key_id = "test_key_2"

    # Fill up to burst limit
    for _ in range(10):  # Burst limit
        await check_rate_limit(redis_client, api_key_id)

    # Next request should be blocked
    allowed, retry_after = await check_rate_limit(redis_client, api_key_id)
    assert allowed is False
    assert retry_after > 0


@pytest.mark.asyncio
async def test_rate_limit_window_reset(redis_client: aioredis.Redis) -> None:
    """Test that rate limit resets after window."""
    import asyncio

    api_key_id = "test_key_3"

    # Make requests
    for _ in range(5):
        await check_rate_limit(redis_client, api_key_id)

    # Wait for window to reset
    await asyncio.sleep(1.1)

    # Should be allowed again
    allowed, _ = await check_rate_limit(redis_client, api_key_id)
    assert allowed is True

