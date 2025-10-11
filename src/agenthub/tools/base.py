"""Base tool interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict

from agenthub.models.schemas import ToolSpec


class BaseTool(ABC):
    """Base class for all tools."""

    @abstractmethod
    def get_spec(self) -> ToolSpec:
        """Get tool specification.
        
        Returns:
            ToolSpec with schema and metadata
        """
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute the tool.
        
        Args:
            **kwargs: Tool arguments
            
        Returns:
            Tool output dict
        """
        pass

    def validate_input(self, **kwargs: Any) -> None:
        """Validate tool input against schema.
        
        Args:
            **kwargs: Tool arguments
            
        Raises:
            ValueError: If validation fails
        """
        spec = self.get_spec()
        required = spec.input_schema.get("required", [])
        
        for field in required:
            if field not in kwargs:
                raise ValueError(f"Missing required field: {field}")

