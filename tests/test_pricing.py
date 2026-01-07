import pytest
from unittest.mock import patch, MagicMock
from coreason_budget.pricing import PricingEngine
from coreason_budget.config import CoreasonBudgetConfig

def test_pricing_engine_overrides() -> None:
    config = CoreasonBudgetConfig(
        redis_url="redis://localhost",
        model_price_overrides={
            "custom-model": {
                "input_cost_per_token": 0.00001,  # $10 per 1M
                "output_cost_per_token": 0.00003  # $30 per 1M
            }
        }
    )
    engine = PricingEngine(config)

    # 1000 input, 1000 output
    cost = engine.calculate_cost("custom-model", 1000, 1000)
    expected = (1000 * 0.00001) + (1000 * 0.00003) # 0.01 + 0.03 = 0.04
    assert cost == pytest.approx(expected)

def test_pricing_engine_litellm() -> None:
    config = CoreasonBudgetConfig(redis_url="redis://localhost")
    engine = PricingEngine(config)

    with patch("coreason_budget.pricing.litellm.completion_cost") as mock_cost:
        mock_cost.return_value = 0.05

        cost = engine.calculate_cost("gpt-4", 500, 200)

        assert cost == 0.05
        mock_cost.assert_called_once_with(
            model="gpt-4",
            prompt=None,
            completion=None,
            total_input_tokens=500,
            total_output_tokens=200
        )

def test_pricing_engine_litellm_failure() -> None:
    config = CoreasonBudgetConfig(redis_url="redis://localhost")
    engine = PricingEngine(config)

    with patch("coreason_budget.pricing.litellm.completion_cost") as mock_cost:
        mock_cost.side_effect = Exception("Model not found")

        with pytest.raises(ValueError, match="Could not calculate cost"):
            engine.calculate_cost("unknown-model", 10, 10)

def test_pricing_engine_override_partial() -> None:
    # Test with only input cost defined (output defaults to 0)
    config = CoreasonBudgetConfig(
        redis_url="redis://localhost",
        model_price_overrides={
            "half-free": {
                "input_cost_per_token": 0.01
            }
        }
    )
    engine = PricingEngine(config)
    cost = engine.calculate_cost("half-free", 100, 100)
    assert cost == 1.0 # 100 * 0.01 + 100 * 0.0
