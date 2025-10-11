"""Ads metrics tool - mock advertising metrics."""

import random
from typing import Any, Dict

from agenthub.models.schemas import ToolSpec
from agenthub.tools.base import BaseTool


class AdsMetricsMockTool(BaseTool):
    """Mock advertising metrics tool."""

    def get_spec(self) -> ToolSpec:
        """Get tool specification."""
        return ToolSpec(
            name="ads_metrics_mock",
            version="1.0.0",
            description="Get advertising metrics for an advertiser. Returns mock data.",
            input_schema={
                "type": "object",
                "properties": {
                    "advertiser_id": {
                        "type": "string",
                        "description": "Advertiser ID",
                    },
                    "metric": {
                        "type": "string",
                        "description": "Metric to retrieve",
                        "enum": ["roas", "spend", "impressions", "clicks", "conversions"],
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Date range",
                        "enum": ["7d", "30d", "90d"],
                        "default": "7d",
                    },
                },
                "required": ["advertiser_id", "metric"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "advertiser_id": {"type": "string"},
                    "metric": {"type": "string"},
                    "date_range": {"type": "string"},
                    "value": {"type": "number"},
                    "trend": {"type": "string"},
                },
            },
            timeout_s=3.0,
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute ads metrics retrieval (mock)."""
        self.validate_input(**kwargs)
        
        advertiser_id = kwargs["advertiser_id"]
        metric = kwargs["metric"]
        date_range = kwargs.get("date_range", "7d")

        # Generate deterministic mock data based on advertiser_id
        seed = hash(advertiser_id + metric + date_range)
        random.seed(seed)

        # Mock values based on metric
        mock_values = {
            "roas": random.uniform(1.5, 5.0),
            "spend": random.uniform(1000, 100000),
            "impressions": random.randint(10000, 1000000),
            "clicks": random.randint(100, 10000),
            "conversions": random.randint(10, 1000),
        }

        value = mock_values.get(metric, 0)
        
        # Mock trend
        trends = ["up", "down", "stable"]
        trend = random.choice(trends)

        return {
            "advertiser_id": advertiser_id,
            "metric": metric,
            "date_range": date_range,
            "value": round(value, 2),
            "trend": trend,
        }


# Register the tool
from agenthub.tools.registry import tool_registry

tool_registry.register(AdsMetricsMockTool())

