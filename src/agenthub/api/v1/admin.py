"""Admin endpoints with extended key management."""

from datetime import datetime
from typing import Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status

from agenthub.auth.api_keys import (
    create_api_key,
    list_api_keys,
    revoke_api_key,
    rotate_api_key,
)
from agenthub.deps import get_api_key_data, get_redis
from agenthub.governance.token_meter import token_meter
from agenthub.models.schemas import APIKeyCreate, APIKeyResponse

router = APIRouter()


def require_admin(api_key_data: Dict[str, str] = Depends(get_api_key_data)) -> Dict[str, str]:
    """Require admin role."""
    if api_key_data.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return api_key_data


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_new_api_key(
    request: APIKeyCreate,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> APIKeyResponse:
    """Create a new API key (admin only)."""
    key_info = await create_api_key(redis, request.role, request.name)

    return APIKeyResponse(
        key_id=key_info["key_id"],
        api_key=key_info["api_key"],
        role=key_info["role"],
        created_at=datetime.fromisoformat(key_info["created_at"]),
    )


@router.post("/api-keys/{key_id}/revoke")
async def revoke_key(
    key_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> Dict[str, str]:
    """Revoke an API key immediately (admin only)."""
    result = await revoke_api_key(redis, key_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )
    
    return {"message": f"API key {key_id} revoked successfully"}


@router.post("/api-keys/{key_id}/rotate", response_model=APIKeyResponse)
async def rotate_key(
    key_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> APIKeyResponse:
    """Rotate an API key - creates new key, revokes old (admin only)."""
    new_key_info = await rotate_api_key(redis, key_id)
    
    if not new_key_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )
    
    return APIKeyResponse(
        key_id=new_key_info["key_id"],
        api_key=new_key_info["api_key"],
        role=new_key_info["role"],
        created_at=datetime.fromisoformat(new_key_info["created_at"]),
    )


@router.get("/api-keys")
async def list_keys(
    status_filter: Optional[str] = Query(None, description="Filter by status (active, revoked)"),
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> List[Dict[str, str]]:
    """List all API keys (admin only)."""
    keys = await list_api_keys(redis, status_filter)
    return keys


@router.get("/api-keys/{key_id}")
async def get_key_info(
    key_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> Dict[str, str]:
    """Get API key details (admin only)."""
    key_data = await redis.hgetall(f"apikey:{key_id}")
    
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found",
        )
    
    decoded = {k.decode(): v.decode() for k, v in key_data.items()}
    
    # Don't return the actual key hash
    decoded.pop("key_hash", None)
    decoded["key_id"] = key_id
    
    return decoded


@router.put("/tenants/{tenant_id}/budget")
async def set_tenant_budget(
    tenant_id: str,
    monthly_cap: float = Query(..., description="Monthly budget in USD"),
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> Dict[str, str]:
    """Set monthly budget cap for a tenant (admin only)."""
    await token_meter.set_tenant_budget(redis, tenant_id, monthly_cap)
    
    return {
        "message": f"Budget set for tenant {tenant_id}",
        "monthly_cap": monthly_cap,
    }


@router.get("/tenants/{tenant_id}/usage")
async def get_tenant_usage(
    tenant_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> Dict[str, float]:
    """Get tenant's current usage (admin only)."""
    usage = await token_meter.get_tenant_usage(redis, tenant_id)
    return usage


@router.get("/health")
async def admin_health(
    api_key_data: Dict[str, str] = Depends(require_admin),
) -> Dict[str, str]:
    """Admin health check."""
    return {"status": "healthy", "role": api_key_data["role"]}
