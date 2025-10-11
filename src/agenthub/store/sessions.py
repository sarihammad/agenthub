"""Redis-based session store."""

import json
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

from agenthub.config import settings
from agenthub.models.schemas import Session


class SessionStore:
    """Redis-based session storage."""

    def __init__(self) -> None:
        """Initialize session store."""
        pass

    async def create(
        self,
        redis_client: aioredis.Redis,
        context: Optional[Dict[str, Any]] = None,
        ttl_s: Optional[int] = None,
    ) -> Session:
        """Create a new session.
        
        Args:
            redis_client: Redis client
            context: Optional initial context
            ttl_s: Optional TTL in seconds
            
        Returns:
            Created Session
        """
        session_id = secrets.token_urlsafe(16)
        ttl = ttl_s or settings.session_ttl_seconds

        session = Session(
            id=session_id,
            ttl_s=ttl,
            context=context or {},
        )

        await self.save(redis_client, session)
        return session

    async def save(
        self,
        redis_client: aioredis.Redis,
        session: Session,
    ) -> None:
        """Save session to Redis.
        
        Args:
            redis_client: Redis client
            session: Session to save
        """
        key = f"session:{session.id}"
        value = session.model_dump_json()
        await redis_client.set(key, value, ex=session.ttl_s)

    async def get(
        self,
        redis_client: aioredis.Redis,
        session_id: str,
    ) -> Optional[Session]:
        """Get session by ID.
        
        Args:
            redis_client: Redis client
            session_id: Session ID
            
        Returns:
            Session or None if not found
        """
        key = f"session:{session_id}"
        value = await redis_client.get(key)
        
        if not value:
            return None

        data = json.loads(value)
        return Session(**data)

    async def append_history(
        self,
        redis_client: aioredis.Redis,
        session_id: str,
        entry: Dict[str, Any],
    ) -> bool:
        """Append an entry to session history.
        
        Args:
            redis_client: Redis client
            session_id: Session ID
            entry: History entry to append
            
        Returns:
            True if successful, False if session not found
        """
        session = await self.get(redis_client, session_id)
        if not session:
            return False

        session.history.append(entry)
        await self.save(redis_client, session)
        return True

    async def update_tokens_cost(
        self,
        redis_client: aioredis.Redis,
        session_id: str,
        tokens: int,
        cost_usd: float,
    ) -> bool:
        """Update session token and cost counters.
        
        Args:
            redis_client: Redis client
            session_id: Session ID
            tokens: Tokens to add
            cost_usd: Cost to add
            
        Returns:
            True if successful, False if session not found
        """
        session = await self.get(redis_client, session_id)
        if not session:
            return False

        session.total_tokens += tokens
        session.total_cost_usd += cost_usd
        await self.save(redis_client, session)
        return True

    async def delete(
        self,
        redis_client: aioredis.Redis,
        session_id: str,
    ) -> bool:
        """Delete a session.
        
        Args:
            redis_client: Redis client
            session_id: Session ID
            
        Returns:
            True if deleted, False if not found
        """
        key = f"session:{session_id}"
        result = await redis_client.delete(key)
        return result > 0


session_store = SessionStore()

