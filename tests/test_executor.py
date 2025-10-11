"""Test executor."""

import pytest
import redis.asyncio as aioredis

from agenthub.executor.executor import executor
from agenthub.models.schemas import Plan, ToolCall


@pytest.mark.asyncio
async def test_executor_runs_plan(redis_client: aioredis.Redis) -> None:
    """Test that executor runs a plan."""
    plan = Plan(
        steps=[
            ToolCall(
                tool="search",
                args={"query": "test query"},
                step_id="step_0",
            )
        ],
        rationale="Test plan",
    )

    result = await executor.execute_plan(redis_client, "test_session", plan)

    assert result.success is True
    assert len(result.steps) == 1
    assert result.steps[0].ok is True
    assert result.steps[0].tool == "search"


@pytest.mark.asyncio
async def test_executor_caches_results(redis_client: aioredis.Redis) -> None:
    """Test that executor caches results."""
    plan = Plan(
        steps=[
            ToolCall(
                tool="search",
                args={"query": "cached query"},
                step_id="step_0",
            )
        ],
        rationale="Test caching",
    )

    # First execution
    result1 = await executor.execute_plan(redis_client, "test_session", plan)
    assert result1.steps[0].cached is False

    # Second execution (should be cached)
    result2 = await executor.execute_plan(redis_client, "test_session", plan)
    assert result2.steps[0].cached is True


@pytest.mark.asyncio
async def test_executor_handles_tool_failure(redis_client: aioredis.Redis) -> None:
    """Test that executor handles tool failures."""
    plan = Plan(
        steps=[
            ToolCall(
                tool="nonexistent_tool",
                args={},
                step_id="step_0",
            )
        ],
        rationale="Test failure",
    )

    result = await executor.execute_plan(redis_client, "test_session", plan)

    assert result.success is False
    assert len(result.steps) == 1
    assert result.steps[0].ok is False
    assert result.steps[0].error is not None

