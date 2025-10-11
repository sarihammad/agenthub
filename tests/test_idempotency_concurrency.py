"""Test idempotency under concurrent load."""

import asyncio

import pytest
import redis.asyncio as aioredis

from agenthub.governance.idempotency import check_idempotency, store_idempotency


@pytest.mark.asyncio
async def test_idempotency_concurrent_writes(redis_client: aioredis.Redis) -> None:
    """Test that concurrent requests with same idempotency key only execute once."""
    idempotency_key = "test_concurrent_key"
    
    # Simulate concurrent requests trying to store same key
    async def try_store(value: int) -> bool:
        """Try to store a value with idempotency key."""
        response = {"value": value, "timestamp": asyncio.get_event_loop().time()}
        return await store_idempotency(redis_client, idempotency_key, response)
    
    # Launch 10 concurrent attempts
    results = await asyncio.gather(*[try_store(i) for i in range(10)])
    
    # Only one should succeed (return True)
    successes = sum(1 for r in results if r is True)
    assert successes == 1, f"Expected 1 success, got {successes}"
    
    # All should now see the cached response
    cached = await check_idempotency(redis_client, idempotency_key)
    assert cached is not None
    assert "value" in cached


@pytest.mark.asyncio
async def test_idempotency_replay_returns_same_response(
    redis_client: aioredis.Redis,
) -> None:
    """Test that replaying idempotency key returns cached response."""
    idempotency_key = "test_replay_key"
    original_response = {
        "session_id": "abc123",
        "status": "created",
        "timestamp": 1697123456,
    }
    
    # First request stores response
    stored = await store_idempotency(redis_client, idempotency_key, original_response)
    assert stored is True
    
    # Replay attempts should get cached response
    for _ in range(5):
        cached = await check_idempotency(redis_client, idempotency_key)
        assert cached == original_response
    
    # Attempting to store again should fail (key exists)
    new_response = {"session_id": "xyz789", "status": "duplicate"}
    stored_again = await store_idempotency(redis_client, idempotency_key, new_response)
    assert stored_again is False
    
    # Cached response should still be original
    cached = await check_idempotency(redis_client, idempotency_key)
    assert cached == original_response


@pytest.mark.asyncio
async def test_idempotency_different_keys_independent(
    redis_client: aioredis.Redis,
) -> None:
    """Test that different idempotency keys are independent."""
    key1 = "test_key_1"
    key2 = "test_key_2"
    
    response1 = {"data": "first"}
    response2 = {"data": "second"}
    
    # Store both
    await store_idempotency(redis_client, key1, response1)
    await store_idempotency(redis_client, key2, response2)
    
    # Each should return its own response
    cached1 = await check_idempotency(redis_client, key1)
    cached2 = await check_idempotency(redis_client, key2)
    
    assert cached1 == response1
    assert cached2 == response2


@pytest.mark.asyncio
async def test_idempotency_ttl_expiry(redis_client: aioredis.Redis) -> None:
    """Test that idempotency keys expire after TTL."""
    import asyncio
    
    idempotency_key = "test_ttl_key"
    response = {"data": "will_expire"}
    
    # Store with short TTL (2 seconds)
    await store_idempotency(redis_client, idempotency_key, response, ttl=2)
    
    # Should exist immediately
    cached = await check_idempotency(redis_client, idempotency_key)
    assert cached == response
    
    # Wait for expiry
    await asyncio.sleep(3)
    
    # Should be gone
    cached_after_expiry = await check_idempotency(redis_client, idempotency_key)
    assert cached_after_expiry is None
    
    # Can store again with same key after expiry
    new_response = {"data": "new_after_expiry"}
    stored = await store_idempotency(redis_client, idempotency_key, new_response)
    assert stored is True


@pytest.mark.asyncio
async def test_idempotency_race_condition_handling(
    redis_client: aioredis.Redis,
) -> None:
    """Test race condition where multiple requests arrive simultaneously."""
    idempotency_key = "test_race_key"
    
    # Create a barrier to ensure all tasks start at same time
    barrier = asyncio.Event()
    results = []
    
    async def racing_store(task_id: int) -> dict:
        """Wait for barrier then try to store."""
        await barrier.wait()
        response = {"task_id": task_id, "data": f"data_{task_id}"}
        success = await store_idempotency(redis_client, idempotency_key, response)
        return {"task_id": task_id, "success": success}
    
    # Create 20 racing tasks
    tasks = [asyncio.create_task(racing_store(i)) for i in range(20)]
    
    # Release all at once
    barrier.set()
    
    # Collect results
    results = await asyncio.gather(*tasks)
    
    # Exactly one should succeed
    successes = [r for r in results if r["success"]]
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    
    # Verify the stored value
    cached = await check_idempotency(redis_client, idempotency_key)
    assert cached is not None
    assert cached["task_id"] == successes[0]["task_id"]

