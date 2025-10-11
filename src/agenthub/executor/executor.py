"""Executor with retries, backoff, and caching."""

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from agenthub.models.schemas import ExecutionResult, Plan, ToolResult
from agenthub.observability.metrics import metrics
from agenthub.store.cache import result_cache
from agenthub.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class Executor:
    """Executor that runs execution plans with retries and caching."""

    def __init__(
        self,
        max_retries: int = 3,
        base_backoff: float = 0.5,
        max_backoff: float = 10.0,
    ) -> None:
        """Initialize executor.
        
        Args:
            max_retries: Maximum number of retries for transient failures
            base_backoff: Base backoff in seconds
            max_backoff: Maximum backoff in seconds
        """
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter.
        
        Args:
            attempt: Attempt number (0-indexed)
            
        Returns:
            Backoff time in seconds
        """
        backoff = min(self.base_backoff * (2**attempt), self.max_backoff)
        jitter = random.uniform(0, backoff * 0.1)
        return backoff + jitter

    async def _execute_step(
        self,
        redis_client: aioredis.Redis,
        tool_name: str,
        args: Dict[str, Any],
        step_id: Optional[str] = None,
    ) -> ToolResult:
        """Execute a single tool with caching and retries.
        
        Args:
            redis_client: Redis client
            tool_name: Tool name
            args: Tool arguments
            step_id: Optional step ID
            
        Returns:
            ToolResult
        """
        start_time = time.time()
        
        # Check cache first
        cached_result = await result_cache.get(redis_client, tool_name, args)
        if cached_result:
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_cache_hit()
            metrics.record_tool_execution(tool_name, "success", latency_ms)
            
            return ToolResult(
                tool=tool_name,
                ok=True,
                output=cached_result,
                latency_ms=latency_ms,
                cached=True,
                step_id=step_id,
            )

        metrics.record_cache_miss()

        # Get tool
        tool = tool_registry.get(tool_name)
        if not tool:
            return ToolResult(
                tool=tool_name,
                ok=False,
                output=None,
                error=f"Tool not found: {tool_name}",
                latency_ms=(time.time() - start_time) * 1000,
                step_id=step_id,
            )

        # Execute with retries
        last_error = None
        for attempt in range(self.max_retries):
            try:
                output = await tool.execute(**args)
                latency_ms = (time.time() - start_time) * 1000

                # Cache successful result
                await result_cache.set(redis_client, tool_name, args, output)

                metrics.record_tool_execution(tool_name, "success", latency_ms)

                return ToolResult(
                    tool=tool_name,
                    ok=True,
                    output=output,
                    latency_ms=latency_ms,
                    cached=False,
                    step_id=step_id,
                )

            except asyncio.TimeoutError as e:
                last_error = f"Timeout: {str(e)}"
                logger.warning(f"Tool {tool_name} timed out (attempt {attempt + 1})")
                
                if attempt < self.max_retries - 1:
                    backoff = self._calculate_backoff(attempt)
                    await asyncio.sleep(backoff)

            except Exception as e:
                last_error = str(e)
                logger.error(f"Tool {tool_name} failed: {e} (attempt {attempt + 1})")

                # Check if error is transient
                is_transient = any(
                    keyword in str(e).lower()
                    for keyword in ["timeout", "connection", "temporary"]
                )

                if is_transient and attempt < self.max_retries - 1:
                    backoff = self._calculate_backoff(attempt)
                    await asyncio.sleep(backoff)
                else:
                    break

        # All retries failed
        latency_ms = (time.time() - start_time) * 1000
        metrics.record_tool_execution(tool_name, "error", latency_ms)

        return ToolResult(
            tool=tool_name,
            ok=False,
            output=None,
            error=last_error or "Unknown error",
            latency_ms=latency_ms,
            step_id=step_id,
        )

    async def execute_plan(
        self,
        redis_client: aioredis.Redis,
        session_id: str,
        plan: Plan,
    ) -> ExecutionResult:
        """Execute a complete plan.
        
        Args:
            redis_client: Redis client
            session_id: Session ID
            plan: Plan to execute
            
        Returns:
            ExecutionResult
        """
        start_time = time.time()
        results: List[ToolResult] = []

        # Execute steps sequentially
        for step in plan.steps:
            result = await self._execute_step(
                redis_client,
                step.tool,
                step.args,
                step.step_id,
            )
            results.append(result)

            # Stop on first failure (can be made configurable)
            if not result.ok:
                logger.warning(f"Step {step.step_id} failed: {result.error}")
                break

        duration_ms = (time.time() - start_time) * 1000

        # Aggregate totals
        total_tokens = sum(r.tokens_in + r.tokens_out for r in results)
        total_cost_usd = 0.0  # Computed by token meter middleware

        # Determine final output (last successful result)
        final_output = None
        success = all(r.ok for r in results)
        for r in reversed(results):
            if r.ok:
                final_output = r.output
                break

        return ExecutionResult(
            session_id=session_id,
            steps=results,
            total_tokens=total_tokens,
            total_cost_usd=total_cost_usd,
            duration_ms=duration_ms,
            success=success,
            final_output=final_output,
        )


executor = Executor()

