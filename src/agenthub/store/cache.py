"""Result caching for tool executions."""

import hashlib
import json
from typing import Any, Dict, Optional

import redis.asyncio as aioredis


class ResultCache:
    """Cache for tool execution results."""

    def __init__(self, ttl: int = 300) -> None:
        """Initialize result cache.
        
        Args:
            ttl: Cache TTL in seconds (default 5 minutes)
        """
        self.ttl = ttl

    def _make_key(self, tool: str, args: Dict[str, Any]) -> str:
        """Generate cache key from tool and args.
        
        Args:
            tool: Tool name
            args: Tool arguments
            
        Returns:
            Cache key
        """
        # Sort args for consistent hashing
        args_str = json.dumps(args, sort_keys=True)
        args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:16]
        return f"cache:tool:{tool}:{args_hash}"

    async def get(
        self,
        redis_client: aioredis.Redis,
        tool: str,
        args: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Get cached result.
        
        Args:
            redis_client: Redis client
            tool: Tool name
            args: Tool arguments
            
        Returns:
            Cached result or None
        """
        key = self._make_key(tool, args)
        value = await redis_client.get(key)
        
        if value:
            return json.loads(value)
        return None

    async def set(
        self,
        redis_client: aioredis.Redis,
        tool: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Cache a result.
        
        Args:
            redis_client: Redis client
            tool: Tool name
            args: Tool arguments
            result: Result to cache
        """
        key = self._make_key(tool, args)
        value = json.dumps(result)
        await redis_client.set(key, value, ex=self.ttl)

    async def invalidate(
        self,
        redis_client: aioredis.Redis,
        tool: str,
        args: Dict[str, Any],
    ) -> bool:
        """Invalidate a cached result.
        
        Args:
            redis_client: Redis client
            tool: Tool name
            args: Tool arguments
            
        Returns:
            True if invalidated, False if not found
        """
        key = self._make_key(tool, args)
        result = await redis_client.delete(key)
        return result > 0


result_cache = ResultCache()

