"""Test tenant budget enforcement."""

import pytest
import redis.asyncio as aioredis

from agenthub.governance.token_meter import TokenMeter


@pytest.mark.asyncio
async def test_check_tenant_budget_within_limit(redis_client: aioredis.Redis) -> None:
    """Test that requests within budget are allowed."""
    meter = TokenMeter()
    tenant_id = "test_tenant_1"
    
    # Set budget
    await meter.set_tenant_budget(redis_client, tenant_id, 100.0)
    
    # Check budget for small request
    allowed, warning = await meter.check_tenant_budget(redis_client, tenant_id, 10.0)
    
    assert allowed is True
    assert warning is None


@pytest.mark.asyncio
async def test_check_tenant_budget_soft_threshold(redis_client: aioredis.Redis) -> None:
    """Test soft threshold warning."""
    meter = TokenMeter()
    tenant_id = "test_tenant_2"
    
    # Set budget and spend close to soft threshold
    await meter.set_tenant_budget(redis_client, tenant_id, 100.0)
    await meter.record_tenant_spend(redis_client, tenant_id, 75.0)
    
    # Check budget (80% threshold)
    allowed, warning = await meter.check_tenant_budget(redis_client, tenant_id, 10.0)
    
    assert allowed is True
    assert warning is not None
    assert "Approaching" in warning


@pytest.mark.asyncio
async def test_check_tenant_budget_hard_limit(redis_client: aioredis.Redis) -> None:
    """Test hard limit enforcement."""
    meter = TokenMeter()
    tenant_id = "test_tenant_3"
    
    # Set budget and spend up to limit
    await meter.set_tenant_budget(redis_client, tenant_id, 100.0)
    await meter.record_tenant_spend(redis_client, tenant_id, 95.0)
    
    # Try to exceed budget
    allowed, warning = await meter.check_tenant_budget(redis_client, tenant_id, 10.0)
    
    assert allowed is False
    assert "exceeded" in warning.lower()


@pytest.mark.asyncio
async def test_tenant_usage_tracking(redis_client: aioredis.Redis) -> None:
    """Test usage tracking and reporting."""
    meter = TokenMeter()
    tenant_id = "test_tenant_4"
    
    # Set budget
    await meter.set_tenant_budget(redis_client, tenant_id, 100.0)
    
    # Record some spend
    await meter.record_tenant_spend(redis_client, tenant_id, 25.0)
    await meter.record_tenant_spend(redis_client, tenant_id, 15.0)
    
    # Get usage
    usage = await meter.get_tenant_usage(redis_client, tenant_id)
    
    assert usage["current_spend"] == 40.0
    assert usage["monthly_cap"] == 100.0
    assert usage["remaining"] == 60.0
    assert usage["usage_percent"] == pytest.approx(40.0)


@pytest.mark.asyncio
async def test_tenant_budget_default(redis_client: aioredis.Redis) -> None:
    """Test default budget for new tenant."""
    meter = TokenMeter()
    tenant_id = "test_tenant_new"
    
    # Don't set explicit budget - should use default
    allowed, warning = await meter.check_tenant_budget(redis_client, tenant_id, 10.0)
    
    assert allowed is True
    
    # Check that default was set
    usage = await meter.get_tenant_usage(redis_client, tenant_id)
    assert usage["monthly_cap"] == 100.0  # Default


@pytest.mark.asyncio
async def test_multiple_tenants_isolated(redis_client: aioredis.Redis) -> None:
    """Test that tenant budgets are isolated."""
    meter = TokenMeter()
    tenant1 = "test_tenant_iso_1"
    tenant2 = "test_tenant_iso_2"
    
    # Set different budgets
    await meter.set_tenant_budget(redis_client, tenant1, 50.0)
    await meter.set_tenant_budget(redis_client, tenant2, 200.0)
    
    # Spend for tenant 1
    await meter.record_tenant_spend(redis_client, tenant1, 40.0)
    
    # Check tenant 1 is close to limit
    usage1 = await meter.get_tenant_usage(redis_client, tenant1)
    assert usage1["current_spend"] == 40.0
    assert usage1["remaining"] == 10.0
    
    # Check tenant 2 is unaffected
    usage2 = await meter.get_tenant_usage(redis_client, tenant2)
    assert usage2["current_spend"] == 0.0
    assert usage2["remaining"] == 200.0

