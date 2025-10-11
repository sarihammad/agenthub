"""Planner with function-calling and tool selection."""

import json
import logging
from typing import Any, Dict, List, Optional

from agenthub.models.schemas import Plan, ToolCall
from agenthub.providers.llm import LLMProvider, get_llm_provider
from agenthub.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class Planner:
    """Planner that creates execution plans using LLM function calling."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None) -> None:
        """Initialize planner.
        
        Args:
            llm_provider: Optional LLM provider (defaults to configured provider)
        """
        self.llm_provider = llm_provider or get_llm_provider()

    async def create_plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        tools_allowed: Optional[List[str]] = None,
    ) -> tuple[Plan, int, int]:
        """Create an execution plan for a goal.
        
        Args:
            goal: The goal to achieve
            context: Optional context dict
            tools_allowed: Optional list of allowed tool names
            
        Returns:
            Tuple of (Plan, tokens_in, tokens_out)
        """
        # Get available tools
        tools = tool_registry.get_openai_tools(filter_names=tools_allowed)

        # Build messages
        system_msg = (
            "You are a helpful AI assistant that creates execution plans. "
            "Given a goal, select the appropriate tools and create a step-by-step plan. "
            "Use function calling to specify which tools to use and their arguments. "
            "Be efficient and avoid unnecessary steps."
        )

        context_str = ""
        if context:
            context_str = f"\n\nContext: {json.dumps(context)}"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Goal: {goal}{context_str}"},
        ]

        # Call LLM with function calling
        response = await self.llm_provider.complete(
            messages=messages,
            tools=tools,
            temperature=0.3,
        )

        # Parse tool calls into steps
        steps: List[ToolCall] = []
        
        if response["tool_calls"]:
            for idx, tc in enumerate(response["tool_calls"]):
                try:
                    args = json.loads(tc["function"]["arguments"])
                    steps.append(
                        ToolCall(
                            tool=tc["function"]["name"],
                            args=args,
                            step_id=f"step_{idx}",
                        )
                    )
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool call arguments: {tc}")

        # If no tool calls, create a simple plan with rationale
        rationale = response.get("content", "")
        if not rationale and steps:
            rationale = f"Execute {len(steps)} steps to achieve the goal."
        elif not rationale:
            rationale = "No actions required or unable to create plan."

        plan = Plan(
            steps=steps,
            rationale=rationale,
            estimated_tokens=response["tokens_in"] + response["tokens_out"],
        )

        return plan, response["tokens_in"], response["tokens_out"]


planner = Planner()

