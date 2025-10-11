"""Sliding window rate limiter using Redis with headers."""

import time
from typing import Dict

import redis.asyncio as aioredis

from agenthub.config import settings


class RateLimitInfo:
    """Rate limit information."""
    
    def __init__(
        self,
        allowed: bool,
        retry_after: int,
        limit: int,
        remaining: int,
        reset_at: float,
    ):
        self.allowed = allowed
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at)),
        }
        
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        
        return headers


async def check_rate_limit(
    redis_client: aioredis.Redis,
    api_key_id: str,
) -> RateLimitInfo:
    """Check if request is rate limited using sliding window.
    
    Args:
        redis_client: Redis client
        api_key_id: API key ID
        
    Returns:
        RateLimitInfo with allowed status and headers
    """
    now = time.time()
    window = 1.0  # 1 second window
    key = f"rl:{api_key_id}"

    # Remove old entries outside the window
    await redis_client.zremrangebyscore(key, 0, now - window)

    # Count requests in current window
    count = await redis_client.zcard(key)

    limit = settings.rate_limit_burst  # Use burst as the hard limit
    remaining = limit - count
    reset_at = now + window

    # Check burst limit
    if count >= settings.rate_limit_burst:
        # Calculate retry after based on oldest entry
        oldest_scores = await redis_client.zrange(key, 0, 0, withscores=True)
        if oldest_scores:
            oldest_time = oldest_scores[0][1]
            retry_after = int(oldest_time + window - now) + 1
        else:
            retry_after = 1
        
        return RateLimitInfo(
            allowed=False,
            retry_after=retry_after,
            limit=limit,
            remaining=0,
            reset_at=reset_at,
        )

    # Add current request
    await redis_client.zadd(key, {str(now): now})  # type: ignore
    await redis_client.expire(key, int(window) + 1)

    return RateLimitInfo(
        allowed=True,
        retry_after=0,
        limit=limit,
        remaining=remaining - 1,  # Account for current request
        reset_at=reset_at,
    )
