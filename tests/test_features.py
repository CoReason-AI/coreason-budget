import pytest
from coreason_budget import BudgetConfig, BudgetManager
from coreason_budget.pricing import PricingEngine
from unittest.mock import MagicMock, patch

def test_config_daily_limit_alias():
    """Test that daily_limit_usd is aliased to daily_user_limit_usd."""
    # Test initialization with the alias
    config = BudgetConfig(daily_limit_usd=50.0)
    assert config.daily_user_limit_usd == 50.0

    # Ensure default is preserved if not provided
    config_default = BudgetConfig()
    assert config_default.daily_user_limit_usd == 10.0

    # Ensure precedence (explicit takes precedence over alias if both provided?
    # Logic: if daily_user_limit_usd missing, use alias.
    # If both present, daily_user_limit_usd should win or error.
    # Our validator: if "daily_limit_usd" in data and "daily_user_limit_usd" not in data
    config_both = BudgetConfig(daily_user_limit_usd=20.0, daily_limit_usd=50.0)
    assert config_both.daily_user_limit_usd == 20.0

def test_pricing_overrides_configured():
    """Test that custom_model_prices are used when configured."""
    custom_prices = {
        "gpt-custom": {
            "input_cost_per_token": 0.0001,
            "output_cost_per_token": 0.0002
        }
    }
    config = BudgetConfig(custom_model_prices=custom_prices)
    pricing = PricingEngine(config)

    # Calculate cost using override
    # 1000 input, 1000 output
    # Cost = (1000 * 0.0001) + (1000 * 0.0002) = 0.1 + 0.2 = 0.3
    cost = pricing.calculate("gpt-custom", 1000, 1000)
    assert cost == pytest.approx(0.3)

    # Ensure other models still try to use litellm
    with patch("coreason_budget.pricing.litellm.completion_cost", return_value=1.0) as mock_litellm:
        cost_std = pricing.calculate("gpt-standard", 100, 100)
        assert cost_std == 1.0
        mock_litellm.assert_called_once()

def test_pricing_overrides_default_empty():
    """Test that default config has empty overrides and uses litellm."""
    config = BudgetConfig()
    pricing = PricingEngine(config)
    assert pricing.config.custom_model_prices == {}

    with patch("coreason_budget.pricing.litellm.completion_cost", return_value=0.5) as mock_litellm:
        cost = pricing.calculate("gpt-4", 10, 10)
        assert cost == 0.5
        mock_litellm.assert_called_once()

@pytest.mark.asyncio
async def test_manager_uses_config_for_pricing():
    """Test that BudgetManager initializes PricingEngine with its config."""
    custom_prices = {
        "test-model": {"input_cost_per_token": 1.0, "output_cost_per_token": 1.0}
    }
    config = BudgetConfig(redis_url="redis://localhost:6379", custom_model_prices=custom_prices)

    # Mock Ledger to avoid real connection attempt during init if needed
    # But RedisLedger only connects on usage.

    manager = BudgetManager(config)

    # Verify manager's pricing engine has the config
    assert manager.pricing.config == config

    # Verify calculation uses the override
    cost = manager.pricing.calculate("test-model", 1, 1)
    assert cost == 2.0

    await manager.close()
