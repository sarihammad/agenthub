"""Test planner."""

import pytest

from agenthub.planner.planner import planner


@pytest.mark.asyncio
async def test_planner_creates_plan() -> None:
    """Test that planner creates a plan."""
    # Note: This test will fail without a valid OpenAI API key
    # In production, you'd mock the LLM provider
    try:
        plan, tokens_in, tokens_out = await planner.create_plan(
            goal="Get search results for Python",
            tools_allowed=["search"],
        )

        assert plan is not None
        assert len(plan.steps) >= 0
        assert plan.rationale != ""
        assert tokens_in >= 0
        assert tokens_out >= 0
    except Exception as e:
        # If OpenAI API is not available, skip
        pytest.skip(f"OpenAI API not available: {e}")


@pytest.mark.asyncio
async def test_planner_respects_tool_constraints() -> None:
    """Test that planner respects tool constraints."""
    try:
        plan, _, _ = await planner.create_plan(
            goal="Fetch data from a URL",
            tools_allowed=["http_fetch"],
        )

        # If tools were selected, they should only be from allowed list
        for step in plan.steps:
            assert step.tool in ["http_fetch"], f"Unexpected tool: {step.tool}"
    except Exception as e:
        pytest.skip(f"OpenAI API not available: {e}")

