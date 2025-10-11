"""API key management with HMAC signing and lifecycle tracking."""

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Dict, Optional

import redis.asyncio as aioredis

from agenthub.config import settings


def _sign_key(key_id: str, secret: str) -> str:
    """Sign a key ID with HMAC."""
    return hmac.new(
        secret.encode(),
        key_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def _hash_key(api_key: str) -> str:
    """Hash an API key for storage (at-rest encryption)."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def _generate_api_key(key_id: str) -> str:
    """Generate a signed API key."""
    signature = _sign_key(key_id, settings.api_key_signing_secret)
    return f"{key_id}.{signature}"


def _parse_api_key(api_key: str) -> tuple[str, str]:
    """Parse API key into key_id and signature."""
    parts = api_key.split(".", 1)
    if len(parts) != 2:
        raise ValueError("Invalid API key format")
    return parts[0], parts[1]


async def create_api_key(
    redis_client: aioredis.Redis,
    role: str,
    name: Optional[str] = None,
) -> Dict[str, str]:
    """Create a new API key.
    
    Args:
        redis_client: Redis client
        role: Role (admin, developer, client)
        name: Optional name for the key
        
    Returns:
        Dict with key_id, api_key, role, created_at
    """
    if role not in ["admin", "developer", "client"]:
        raise ValueError("Invalid role")

    key_id = secrets.token_urlsafe(16)
    api_key = _generate_api_key(key_id)
    created_at = datetime.utcnow().isoformat()

    # Hash the API key for storage
    key_hash = _hash_key(api_key)

    # Store in Redis hash
    key_data = {
        "role": role,
        "created_at": created_at,
        "status": "active",
        "key_hash": key_hash,
        "last_used": "",
    }
    if name:
        key_data["name"] = name

    await redis_client.hset(f"apikey:{key_id}", mapping=key_data)  # type: ignore

    return {
        "key_id": key_id,
        "api_key": api_key,
        "role": role,
        "created_at": created_at,
    }


async def validate_api_key(
    redis_client: aioredis.Redis,
    api_key: str,
) -> Optional[Dict[str, str]]:
    """Validate an API key and update last_used timestamp.
    
    Args:
        redis_client: Redis client
        api_key: API key to validate
        
    Returns:
        Dict with key_id, role, status, created_at if valid, None otherwise
    """
    try:
        key_id, signature = _parse_api_key(api_key)
    except ValueError:
        return None

    # Verify signature
    expected_signature = _sign_key(key_id, settings.api_key_signing_secret)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    # Fetch from Redis
    key_data = await redis_client.hgetall(f"apikey:{key_id}")
    if not key_data:
        return None

    # Decode bytes to str
    decoded_data = {k.decode(): v.decode() for k, v in key_data.items()}

    # Check status - deny revoked immediately
    if decoded_data.get("status") != "active":
        return None

    # Update last_used timestamp (async, fire-and-forget)
    try:
        now = datetime.utcnow().isoformat()
        await redis_client.hset(f"apikey:{key_id}", "last_used", now)
    except Exception:
        pass  # Don't fail validation if timestamp update fails

    return {
        "key_id": key_id,
        "role": decoded_data["role"],
        "status": decoded_data["status"],
        "created_at": decoded_data["created_at"],
        "last_used": decoded_data.get("last_used", ""),
    }


async def revoke_api_key(
    redis_client: aioredis.Redis,
    key_id: str,
) -> bool:
    """Revoke an API key immediately.
    
    Args:
        redis_client: Redis client
        key_id: Key ID to revoke
        
    Returns:
        True if revoked, False if not found
    """
    exists = await redis_client.exists(f"apikey:{key_id}")
    if not exists:
        return False

    revoked_at = datetime.utcnow().isoformat()
    await redis_client.hset(f"apikey:{key_id}", "status", "revoked")
    await redis_client.hset(f"apikey:{key_id}", "revoked_at", revoked_at)
    return True


async def rotate_api_key(
    redis_client: aioredis.Redis,
    old_key_id: str,
) -> Optional[Dict[str, str]]:
    """Rotate an API key - create new key with same role, revoke old.
    
    Args:
        redis_client: Redis client
        old_key_id: Old key ID to rotate
        
    Returns:
        New key info or None if old key not found
    """
    # Get old key data
    old_data = await redis_client.hgetall(f"apikey:{old_key_id}")
    if not old_data:
        return None

    decoded_old = {k.decode(): v.decode() for k, v in old_data.items()}
    
    # Create new key with same role and name
    new_key_info = await create_api_key(
        redis_client,
        decoded_old["role"],
        decoded_old.get("name"),
    )

    # Revoke old key
    await revoke_api_key(redis_client, old_key_id)

    return new_key_info


async def list_api_keys(
    redis_client: aioredis.Redis,
    status_filter: Optional[str] = None,
) -> list[Dict[str, str]]:
    """List all API keys (for admin).
    
    Args:
        redis_client: Redis client
        status_filter: Optional filter by status (active, revoked)
        
    Returns:
        List of key metadata (without actual keys)
    """
    keys = []
    cursor = 0
    
    # Scan for all apikey:* keys
    while True:
        cursor, batch = await redis_client.scan(cursor, match="apikey:*", count=100)
        
        for key in batch:
            key_id = key.decode().split(":")[1]
            key_data = await redis_client.hgetall(key)
            
            if not key_data:
                continue
                
            decoded = {k.decode(): v.decode() for k, v in key_data.items()}
            
            # Apply status filter
            if status_filter and decoded.get("status") != status_filter:
                continue
            
            keys.append({
                "key_id": key_id,
                "role": decoded.get("role", ""),
                "status": decoded.get("status", ""),
                "name": decoded.get("name", ""),
                "created_at": decoded.get("created_at", ""),
                "last_used": decoded.get("last_used", ""),
                "revoked_at": decoded.get("revoked_at", ""),
            })
        
        if cursor == 0:
            break
    
    return keys
