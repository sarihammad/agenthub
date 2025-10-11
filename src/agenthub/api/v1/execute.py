"""Execution endpoints."""

from typing import Dict, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Header, status

from agenthub.deps import get_api_key_data, get_redis
from agenthub.executor.executor import executor
from agenthub.governance.idempotency import check_idempotency, store_idempotency
from agenthub.governance.token_meter import token_meter
from agenthub.models.schemas import ExecuteRequest, ExecutionResult
from agenthub.observability.metrics import metrics
from agenthub.store.sessions import session_store

router = APIRouter()


@router.post("/execute", response_model=ExecutionResult)
async def execute_plan(
    request: ExecuteRequest,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(get_api_key_data),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> ExecutionResult:
    """Execute a plan."""
    # Check idempotency
    if idempotency_key:
        cached_result = await check_idempotency(redis, idempotency_key)
        if cached_result:
            return ExecutionResult(**cached_result)

    # Verify session exists
    session = await session_store.get(redis, request.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {request.session_id} not found",
        )

    # Execute plan
    result = await executor.execute_plan(redis, request.session_id, request.plan)

    # Calculate cost
    from agenthub.config import settings

    cost = token_meter.calculate_cost(
        settings.openai_model,
        result.total_tokens // 2,  # Rough split
        result.total_tokens // 2,
    )
    result.total_cost_usd = cost

    # Record metrics
    metrics.record_cost(settings.openai_model, cost)

    # Update session
    await session_store.update_tokens_cost(
        redis,
        request.session_id,
        result.total_tokens,
        cost,
    )
    await session_store.append_history(
        redis,
        request.session_id,
        {"type": "execution", "result": result.model_dump()},
    )

    # Store for idempotency
    if idempotency_key:
        await store_idempotency(redis, idempotency_key, result.model_dump())

    return result

