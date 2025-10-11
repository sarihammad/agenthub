"""Planning endpoints."""

from typing import Dict

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status

from agenthub.deps import get_api_key_data, get_redis
from agenthub.governance.token_meter import token_meter
from agenthub.models.schemas import Plan, PlanRequest
from agenthub.observability.metrics import metrics
from agenthub.planner.planner import planner
from agenthub.store.sessions import session_store

router = APIRouter()


@router.post("/plan", response_model=Plan)
async def create_plan(
    request: PlanRequest,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(get_api_key_data),
) -> Plan:
    """Create an execution plan for a goal."""
    # Verify session exists
    session = await session_store.get(redis, request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )

    # Merge session context with request context
    combined_context = {**session.context}
    if request.context:
        combined_context.update(request.context)

    # Create plan
    plan, tokens_in, tokens_out = await planner.create_plan(
        goal=request.goal,
        context=combined_context,
        tools_allowed=request.tools_allowed,
    )

    # Record metrics
    from agenthub.config import settings

    cost = token_meter.calculate_cost(settings.openai_model, tokens_in, tokens_out)
    metrics.record_tokens("input", settings.openai_model, tokens_in)
    metrics.record_tokens("output", settings.openai_model, tokens_out)
    metrics.record_cost(settings.openai_model, cost)

    # Update session
    await session_store.update_tokens_cost(
        redis,
        request.session_id,
        tokens_in + tokens_out,
        cost,
    )

    return plan

