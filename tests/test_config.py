import pytest
from coreason_budget.config import CoreasonBudgetConfig
from _pytest.monkeypatch import MonkeyPatch

def test_config_defaults() -> None:
    # We need to ensure required fields are provided
    config = CoreasonBudgetConfig(redis_url="redis://localhost:6379")
    assert config.redis_url == "redis://localhost:6379"
    assert config.daily_user_limit_usd == 10.0
    assert config.daily_global_limit_usd == 5000.0

def test_config_overrides() -> None:
    config = CoreasonBudgetConfig(
        redis_url="redis://localhost:6379",
        daily_user_limit_usd=100.0,
        model_price_overrides={"gpt-4": {"input_cost_per_token": 0.01}}
    )
    assert config.daily_user_limit_usd == 100.0
    assert config.model_price_overrides["gpt-4"]["input_cost_per_token"] == 0.01

def test_config_env_vars(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("COREASON_BUDGET_REDIS_URL", "redis://env:6379")
    monkeypatch.setenv("COREASON_BUDGET_DAILY_USER_LIMIT_USD", "25.0")

    config = CoreasonBudgetConfig()
    assert config.redis_url == "redis://env:6379"
    assert config.daily_user_limit_usd == 25.0
