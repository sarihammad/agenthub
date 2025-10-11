"""Role-based access control decorators."""

from functools import wraps
from typing import Callable, List

from fastapi import HTTPException, status


def require_role(allowed_roles: List[str]) -> Callable:
    """Decorator to enforce RBAC on endpoints.
    
    Args:
        allowed_roles: List of allowed roles (e.g., ["admin", "developer"])
        
    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):  # type: ignore
            # Extract api_key_data from kwargs (injected by dependency)
            api_key_data = kwargs.get("api_key_data")
            if not api_key_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            user_role = api_key_data.get("role")
            if user_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required roles: {allowed_roles}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator

