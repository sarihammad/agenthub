"""Dependency injection helpers."""

import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Header, Request, status

from agenthub.auth.api_keys import validate_api_key
from agenthub.config import settings

logger = logging.getLogger(__name__)

# Global Redis client
_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Get Redis client dependency."""
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
    return _redis_client


async def get_api_key_data(
    authorization: Optional[str] = Header(None),
    redis: aioredis.Redis = Depends(get_redis),
) -> Dict[str, str]:
    """Extract and validate API key from Authorization header.
    
    Args:
        authorization: Authorization header
        redis: Redis client
        
    Returns:
        API key data dict
        
    Raises:
        HTTPException: If authentication fails
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    # Extract Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <api_key>",
        )

    api_key = parts[1]

    # Validate
    key_data = await validate_api_key(redis, api_key)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    return key_data


def get_client_ip(request: Request) -> str:
    """Extract client IP from request.
    
    Args:
        request: FastAPI request
        
    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header first
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    # Fall back to client host
    return request.client.host if request.client else "unknown"

