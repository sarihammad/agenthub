"""Retrieve document tool - mock vectorstore retrieval."""

from typing import Any, Dict

from agenthub.models.schemas import ToolSpec
from agenthub.providers.vectorstore import mock_vectorstore
from agenthub.tools.base import BaseTool


class RetrieveDocTool(BaseTool):
    """Retrieve documents from mock vectorstore."""

    def get_spec(self) -> ToolSpec:
        """Get tool specification."""
        return ToolSpec(
            name="retrieve_doc",
            version="1.0.0",
            description="Retrieve a document by ID from the knowledge base.",
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "Document ID to retrieve",
                    },
                },
                "required": ["doc_id"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
            timeout_s=2.0,
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute document retrieval."""
        self.validate_input(**kwargs)
        
        doc_id = kwargs["doc_id"]
        document = mock_vectorstore.retrieve(doc_id)
        
        return document


# Register the tool
from agenthub.tools.registry import tool_registry

tool_registry.register(RetrieveDocTool())

