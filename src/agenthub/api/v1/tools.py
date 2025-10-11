"""Tools endpoints."""

from typing import Dict, List

from fastapi import APIRouter, Depends

from agenthub.deps import get_api_key_data
from agenthub.models.schemas import ToolSpec
from agenthub.tools.registry import tool_registry

router = APIRouter()


@router.get("/tools", response_model=List[ToolSpec])
async def list_tools(
    api_key_data: Dict[str, str] = Depends(get_api_key_data),
) -> List[ToolSpec]:
    """List available tools."""
    return tool_registry.list_tools()

