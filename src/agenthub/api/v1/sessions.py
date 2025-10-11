"""Session management endpoints."""

from typing import Dict

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status

from agenthub.deps import get_api_key_data, get_redis
from agenthub.models.schemas import CreateSessionRequest, CreateSessionResponse
from agenthub.store.sessions import session_store

router = APIRouter()


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(get_api_key_data),
) -> CreateSessionResponse:
    """Create a new session."""
    session = await session_store.create(
        redis,
        context=request.context,
        ttl_s=request.ttl_s,
    )

    return CreateSessionResponse(
        session_id=session.id,
        created_at=session.started_at,
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(get_api_key_data),
) -> Dict:
    """Get session by ID."""
    session = await session_store.get(redis, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Mask sensitive data before returning
    from agenthub.governance.masking import mask_sensitive_data

    return mask_sensitive_data(session.model_dump())

