"""Standardized error responses."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standardized error envelope."""

    code: str
    message: str
    trace_id: str
    details: Optional[Dict[str, Any]] = None


def create_error_response(
    code: str,
    message: str,
    trace_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> ErrorResponse:
    """Create a standardized error response.
    
    Args:
        code: Error code (e.g., RATE_LIMIT_EXCEEDED, INVALID_INPUT)
        message: Human-readable error message
        trace_id: Trace ID for correlation
        details: Optional additional details
        
    Returns:
        ErrorResponse
    """
    # Sanitize message to not leak secrets
    from agenthub.governance.masking import mask_sensitive_data
    
    safe_message = mask_sensitive_data(message)
    safe_details = mask_sensitive_data(details) if details else None
    
    return ErrorResponse(
        code=code,
        message=safe_message,
        trace_id=trace_id,
        details=safe_details,
    )

