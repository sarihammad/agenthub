"""Token metering and cost calculation with tenant budgets."""

import logging
from typing import Dict, Optional

import redis.asyncio as aioredis

from agenthub.config import settings

logger = logging.getLogger(__name__)


class TokenMeter:
    """Token and cost metering with tenant budget enforcement."""

    def __init__(self) -> None:
        """Initialize token meter."""
        self.pricing: Dict[str, Dict[str, float]] = {
            settings.openai_model: {
                "input": settings.openai_price_input,
                "output": settings.openai_price_output,
            }
        }

    def calculate_cost(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> float:
        """Calculate cost in USD.
        
        Args:
            model: Model name
            tokens_in: Input tokens
            tokens_out: Output tokens
            
        Returns:
            Cost in USD
        """
        if model not in self.pricing:
            return 0.0

        prices = self.pricing[model]
        cost_in = (tokens_in / 1000.0) * prices["input"]
        cost_out = (tokens_out / 1000.0) * prices["output"]
        return cost_in + cost_out

    def add_model_pricing(
        self,
        model: str,
        input_price: float,
        output_price: float,
    ) -> None:
        """Add pricing for a model.
        
        Args:
            model: Model name
            input_price: Price per 1K input tokens
            output_price: Price per 1K output tokens
        """
        self.pricing[model] = {
            "input": input_price,
            "output": output_price,
        }

    async def check_tenant_budget(
        self,
        redis_client: aioredis.Redis,
        tenant_id: str,
        cost_usd: float,
        soft_threshold: float = 0.8,
    ) -> tuple[bool, Optional[str]]:
        """Check if tenant is within monthly budget.
        
        Args:
            redis_client: Redis client
            tenant_id: Tenant identifier (could be api_key_id)
            cost_usd: Cost of current request
            soft_threshold: Soft threshold ratio (0.8 = 80%)
            
        Returns:
            Tuple of (allowed, warning_message)
        """
        # Get tenant budget config (default $100/month)
        budget_key = f"tenant_budget:{tenant_id}"
        budget_data = await redis_client.hgetall(budget_key)
        
        if not budget_data:
            # Set default budget
            monthly_cap = 100.0  # $100 default
            await redis_client.hset(budget_key, "monthly_cap", str(monthly_cap))
        else:
            monthly_cap = float(budget_data.get(b"monthly_cap", b"100.0"))
        
        # Get current month spend
        from datetime import datetime
        month_key = datetime.utcnow().strftime("%Y-%m")
        spend_key = f"tenant_spend:{tenant_id}:{month_key}"
        
        current_spend = await redis_client.get(spend_key)
        current_spend_float = float(current_spend) if current_spend else 0.0
        
        projected_spend = current_spend_float + cost_usd
        
        # Hard limit check
        if projected_spend > monthly_cap:
            logger.warning(
                f"Tenant {tenant_id} exceeds monthly budget: "
                f"${projected_spend:.2f} > ${monthly_cap:.2f}"
            )
            return False, f"Monthly budget exceeded: ${projected_spend:.2f} / ${monthly_cap:.2f}"
        
        # Soft threshold warning
        if projected_spend > monthly_cap * soft_threshold:
            warning = (
                f"Approaching monthly budget: ${projected_spend:.2f} / ${monthly_cap:.2f} "
                f"({(projected_spend/monthly_cap)*100:.1f}%)"
            )
            logger.info(f"Tenant {tenant_id}: {warning}")
            return True, warning
        
        return True, None

    async def record_tenant_spend(
        self,
        redis_client: aioredis.Redis,
        tenant_id: str,
        cost_usd: float,
    ) -> None:
        """Record tenant spend for the current month.
        
        Args:
            redis_client: Redis client
            tenant_id: Tenant identifier
            cost_usd: Cost to record
        """
        from datetime import datetime
        month_key = datetime.utcnow().strftime("%Y-%m")
        spend_key = f"tenant_spend:{tenant_id}:{month_key}"
        
        # Increment spend atomically
        await redis_client.incrbyfloat(spend_key, cost_usd)
        
        # Set expiry to 90 days to auto-cleanup old months
        await redis_client.expire(spend_key, 90 * 86400)

    async def set_tenant_budget(
        self,
        redis_client: aioredis.Redis,
        tenant_id: str,
        monthly_cap: float,
    ) -> None:
        """Set monthly budget cap for a tenant.
        
        Args:
            redis_client: Redis client
            tenant_id: Tenant identifier
            monthly_cap: Monthly budget in USD
        """
        budget_key = f"tenant_budget:{tenant_id}"
        await redis_client.hset(budget_key, "monthly_cap", str(monthly_cap))

    async def get_tenant_usage(
        self,
        redis_client: aioredis.Redis,
        tenant_id: str,
    ) -> Dict[str, float]:
        """Get tenant's current month usage.
        
        Args:
            redis_client: Redis client
            tenant_id: Tenant identifier
            
        Returns:
            Dict with current_spend, monthly_cap, remaining
        """
        from datetime import datetime
        month_key = datetime.utcnow().strftime("%Y-%m")
        spend_key = f"tenant_spend:{tenant_id}:{month_key}"
        budget_key = f"tenant_budget:{tenant_id}"
        
        current_spend = await redis_client.get(spend_key)
        current_spend_float = float(current_spend) if current_spend else 0.0
        
        budget_data = await redis_client.hgetall(budget_key)
        monthly_cap = float(budget_data.get(b"monthly_cap", b"100.0")) if budget_data else 100.0
        
        return {
            "current_spend": current_spend_float,
            "monthly_cap": monthly_cap,
            "remaining": max(0, monthly_cap - current_spend_float),
            "usage_percent": (current_spend_float / monthly_cap * 100) if monthly_cap > 0 else 0,
        }


token_meter = TokenMeter()
