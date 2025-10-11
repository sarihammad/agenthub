"""Idempotency key handling."""

import json
from typing import Any, Optional

import redis.asyncio as aioredis


async def check_idempotency(
    redis_client: aioredis.Redis,
    idempotency_key: str,
) -> Optional[Any]:
    """Check if idempotency key exists and return stored response.
    
    Args:
        redis_client: Redis client
        idempotency_key: Idempotency key
        
    Returns:
        Stored response if exists, None otherwise
    """
    key = f"idempotency:{idempotency_key}"
    value = await redis_client.get(key)
    if value:
        return json.loads(value)
    return None


async def store_idempotency(
    redis_client: aioredis.Redis,
    idempotency_key: str,
    response: Any,
    ttl: int = 86400,
) -> bool:
    """Store response for idempotency key.
    
    Args:
        redis_client: Redis client
        idempotency_key: Idempotency key
        response: Response to store
        ttl: TTL in seconds (default 24 hours)
        
    Returns:
        True if stored (was new), False if already existed
    """
    key = f"idempotency:{idempotency_key}"
    value = json.dumps(response)
    
    # Use SETNX to only set if not exists
    result = await redis_client.set(key, value, nx=True, ex=ttl)
    return bool(result)

