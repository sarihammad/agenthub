"""Test token metering."""

from agenthub.governance.token_meter import TokenMeter


def test_calculate_cost() -> None:
    """Test cost calculation."""
    meter = TokenMeter()
    meter.add_model_pricing("test-model", 0.001, 0.002)

    # 1000 input tokens + 500 output tokens
    cost = meter.calculate_cost("test-model", 1000, 500)

    # Expected: (1000 / 1000) * 0.001 + (500 / 1000) * 0.002 = 0.001 + 0.001 = 0.002
    assert cost == pytest.approx(0.002)


def test_calculate_cost_unknown_model() -> None:
    """Test cost calculation for unknown model."""
    meter = TokenMeter()

    cost = meter.calculate_cost("unknown-model", 1000, 500)
    assert cost == 0.0


def test_add_model_pricing() -> None:
    """Test adding model pricing."""
    meter = TokenMeter()
    meter.add_model_pricing("custom-model", 0.0005, 0.0015)

    cost = meter.calculate_cost("custom-model", 2000, 1000)
    # Expected: (2000 / 1000) * 0.0005 + (1000 / 1000) * 0.0015 = 0.001 + 0.0015 = 0.0025
    assert cost == pytest.approx(0.0025)

