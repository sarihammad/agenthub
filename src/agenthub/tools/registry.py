"""Tool registry for managing available tools."""

from typing import Dict, List, Optional

from agenthub.models.schemas import ToolSpec
from agenthub.tools.base import BaseTool


class ToolRegistry:
    """Registry for available tools."""

    def __init__(self) -> None:
        """Initialize tool registry."""
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool.
        
        Args:
            tool: Tool instance to register
        """
        spec = tool.get_spec()
        self._tools[spec.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool instance or None
        """
        return self._tools.get(name)

    def list_tools(self, filter_names: Optional[List[str]] = None) -> List[ToolSpec]:
        """List available tools.
        
        Args:
            filter_names: Optional list of tool names to filter by
            
        Returns:
            List of ToolSpec
        """
        tools = self._tools.values()
        if filter_names:
            tools = [t for t in tools if t.get_spec().name in filter_names]
        return [tool.get_spec() for tool in tools]

    def get_openai_tools(
        self, filter_names: Optional[List[str]] = None
    ) -> List[Dict]:
        """Get tools in OpenAI function-calling format.
        
        Args:
            filter_names: Optional list of tool names to filter by
            
        Returns:
            List of tool definitions for OpenAI
        """
        specs = self.list_tools(filter_names)
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_schema,
                },
            }
            for spec in specs
        ]


# Global registry
tool_registry = ToolRegistry()

