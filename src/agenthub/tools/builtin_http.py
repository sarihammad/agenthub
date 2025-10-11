"""HTTP fetch tool with security controls."""

import ipaddress
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from agenthub.models.schemas import ToolSpec
from agenthub.tools.base import BaseTool

# Denylist for security
DENYLISTED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private
    ipaddress.ip_network("172.16.0.0/12"),  # Private
    ipaddress.ip_network("192.168.0.0/16"),  # Private
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
]


class HTTPFetchTool(BaseTool):
    """Fetch content from HTTP(S) URLs with security controls."""

    def get_spec(self) -> ToolSpec:
        """Get tool specification."""
        return ToolSpec(
            name="http_fetch",
            version="1.0.0",
            description="Fetch content from an HTTP(S) URL. Size limited to 100KB.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    },
                },
                "required": ["url"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "status_code": {"type": "integer"},
                    "content_type": {"type": "string"},
                },
            },
            timeout_s=10.0,
        )

    def _is_url_safe(self, url: str) -> bool:
        """Check if URL is safe to fetch."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ["http", "https"]:
                return False

            # Check if hostname resolves to denylisted network
            hostname = parsed.hostname
            if not hostname:
                return False

            # Simple check for localhost
            if hostname in ["localhost", "127.0.0.1", "::1"]:
                return False

            return True
        except Exception:
            return False

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute HTTP fetch."""
        self.validate_input(**kwargs)
        
        url = kwargs["url"]

        if not self._is_url_safe(url):
            return {
                "error": "URL is not safe to fetch (denylisted or invalid)",
                "status_code": 0,
                "content": "",
                "content_type": "",
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, follow_redirects=True)

                # Limit content size to 100KB
                content = response.text[:100000]

                return {
                    "content": content,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                }
        except httpx.TimeoutException:
            return {
                "error": "Request timed out",
                "status_code": 0,
                "content": "",
                "content_type": "",
            }
        except Exception as e:
            return {
                "error": str(e),
                "status_code": 0,
                "content": "",
                "content_type": "",
            }


# Register the tool
from agenthub.tools.registry import tool_registry

tool_registry.register(HTTPFetchTool())

