"""Test rate limit headers."""

import pytest
import redis.asyncio as aioredis

from agenthub.governance.rate_limiter import check_rate_limit


@pytest.mark.asyncio
async def test_rate_limit_headers_success(redis_client: aioredis.Redis) -> None:
    """Test rate limit headers on successful request."""
    api_key_id = "test_key_headers_1"
    
    rate_limit_info = await check_rate_limit(redis_client, api_key_id)
    
    assert rate_limit_info.allowed is True
    
    headers = rate_limit_info.to_headers()
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    assert "Retry-After" not in headers  # Only on 429


@pytest.mark.asyncio
async def test_rate_limit_headers_on_block(redis_client: aioredis.Redis) -> None:
    """Test rate limit headers when blocked."""
    api_key_id = "test_key_headers_2"
    
    # Exhaust rate limit
    for _ in range(10):  # Burst limit
        await check_rate_limit(redis_client, api_key_id)
    
    # Next request should be blocked
    rate_limit_info = await check_rate_limit(redis_client, api_key_id)
    
    assert rate_limit_info.allowed is False
    
    headers = rate_limit_info.to_headers()
    assert headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in headers
    assert int(headers["Retry-After"]) > 0


@pytest.mark.asyncio
async def test_rate_limit_remaining_decreases(redis_client: aioredis.Redis) -> None:
    """Test that remaining counter decreases with requests."""
    api_key_id = "test_key_headers_3"
    
    # First request
    info1 = await check_rate_limit(redis_client, api_key_id)
    remaining1 = int(info1.to_headers()["X-RateLimit-Remaining"])
    
    # Second request
    info2 = await check_rate_limit(redis_client, api_key_id)
    remaining2 = int(info2.to_headers()["X-RateLimit-Remaining"])
    
    # Remaining should decrease
    assert remaining2 < remaining1


@pytest.mark.asyncio
async def test_rate_limit_reset_timestamp(redis_client: aioredis.Redis) -> None:
    """Test that reset timestamp is in the future."""
    import time
    
    api_key_id = "test_key_headers_4"
    
    now = time.time()
    rate_limit_info = await check_rate_limit(redis_client, api_key_id)
    
    headers = rate_limit_info.to_headers()
    reset_time = float(headers["X-RateLimit-Reset"])
    
    assert reset_time > now
    assert reset_time < now + 2  # Within 2 seconds (1 second window + buffer)

