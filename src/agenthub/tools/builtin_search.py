"""Search tool - mock web search."""

from typing import Any, Dict, List

from agenthub.models.schemas import ToolSpec
from agenthub.tools.base import BaseTool


class SearchTool(BaseTool):
    """Mock web search tool."""

    def get_spec(self) -> ToolSpec:
        """Get tool specification."""
        return ToolSpec(
            name="search",
            version="1.0.0",
            description="Search the web for information. Returns mock search results.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "snippet": {"type": "string"},
                            },
                        },
                    },
                },
            },
            timeout_s=5.0,
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute search (mock implementation)."""
        self.validate_input(**kwargs)
        
        query = kwargs["query"]
        num_results = kwargs.get("num_results", 5)

        # Mock results based on query
        mock_results: List[Dict[str, str]] = [
            {
                "title": f"Result {i+1} for: {query}",
                "url": f"https://example.com/result-{i+1}",
                "snippet": f"This is a mock search result #{i+1} related to {query}.",
            }
            for i in range(min(num_results, 10))
        ]

        return {"results": mock_results}


# Register the tool
from agenthub.tools.registry import tool_registry

tool_registry.register(SearchTool())

