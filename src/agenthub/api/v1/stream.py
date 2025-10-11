"""Streaming endpoints with SSE."""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse

from agenthub.deps import get_api_key_data, get_redis
from agenthub.executor.executor import executor
from agenthub.store.sessions import session_store

router = APIRouter()
logger = logging.getLogger(__name__)


async def event_generator(
    redis: aioredis.Redis,
    session_id: str,
) -> AsyncGenerator[Dict, None]:
    """Generate SSE events for a session.
    
    Args:
        redis: Redis client
        session_id: Session ID
        
    Yields:
        SSE event dicts
    """
    # Verify session exists
    session = await session_store.get(redis, session_id)
    if not session:
        yield {
            "event": "error",
            "data": json.dumps({"error": f"Session {session_id} not found"}),
        }
        return

    # Send initial event
    yield {
        "event": "connected",
        "data": json.dumps({"session_id": session_id}),
    }

    # Stream session history (simplified - in production, use pub/sub)
    # For now, just send the current session state
    yield {
        "event": "session",
        "data": json.dumps({
            "session_id": session.id,
            "total_tokens": session.total_tokens,
            "total_cost_usd": session.total_cost_usd,
        }),
    }

    # Send heartbeat and check for updates
    heartbeat_interval = 15  # seconds
    last_heartbeat = asyncio.get_event_loop().time()

    for _ in range(10):  # Limit stream duration for demo
        await asyncio.sleep(1)

        current_time = asyncio.get_event_loop().time()
        if current_time - last_heartbeat >= heartbeat_interval:
            yield {
                "event": "heartbeat",
                "data": json.dumps({"timestamp": current_time}),
            }
            last_heartbeat = current_time

    # Send final event
    yield {
        "event": "final",
        "data": json.dumps({"status": "completed"}),
    }


@router.get("/stream")
async def stream_session(
    session_id: str = Query(..., description="Session ID to stream"),
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(get_api_key_data),
) -> EventSourceResponse:
    """Stream session events via Server-Sent Events."""
    return EventSourceResponse(event_generator(redis, session_id))

