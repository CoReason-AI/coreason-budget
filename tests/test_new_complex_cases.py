import os
from unittest.mock import patch

import pytest

from coreason_budget import BudgetConfig, BudgetManager


@pytest.mark.asyncio
async def test_record_spend_optional_context(manager: BudgetManager) -> None:
    """
    Test record_spend with project_id=None and model=None.
    Verify:
    1. No errors raised.
    2. User and Global limits are incremented.
    3. Project limit is NOT incremented (key not created).
    4. Metrics logs contain "unknown" tags.
    """
    user_id = "user_opt"
    amount = 5.0

    # Spy on logger to check for "unknown" tags
    with patch("coreason_budget.guard.logger") as mock_logger:
        await manager.record_spend(user_id, amount, project_id=None, model=None)

        # Verify logging call
        # The call in code is: logger.info("...{}, {}, {}...", amount, safe_model, safe_project_id, user_id)
        args, kwargs = mock_logger.info.call_args

        # args[0] is the format string
        assert "METRIC: finops.spend.total" in args[0]

        # Verify the arguments passed to the format string
        # args[1] = amount
        # args[2] = safe_model
        # args[3] = safe_project_id
        # args[4] = user_id
        assert args[1] == amount
        assert args[2] == "unknown"  # model
        assert args[3] == "unknown"  # project_id
        assert args[4] == user_id

    # Verify Redis State
    date_str = manager.guard._get_date_str()

    # User key
    user_key = f"spend:v1:user:{user_id}:{date_str}"
    assert await manager.ledger.get_usage(user_key) == amount

    # Global key
    global_key = f"spend:v1:global:{date_str}"
    assert await manager.ledger.get_usage(global_key) == amount

    # Project key should NOT exist for "None"
    assert await manager.ledger.get_usage(f"spend:v1:project:None:{date_str}") == 0.0
    assert await manager.ledger.get_usage(f"spend:v1:project:unknown:{date_str}") == 0.0


@pytest.mark.asyncio
async def test_whitespace_validation(manager: BudgetManager) -> None:
    """Test whitespace-only strings raise ValueError."""

    # Mandatory user_id
    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        await manager.record_spend("   ", 1.0)

    # Optional project_id provided but empty/whitespace
    with pytest.raises(ValueError, match="project_id must be a non-empty string"):
        await manager.record_spend("user_1", 1.0, project_id="   ")

    # Optional model provided but empty/whitespace
    with pytest.raises(ValueError, match="model must be a non-empty string"):
        await manager.record_spend("user_1", 1.0, model="\t")


@pytest.mark.asyncio
async def test_non_finite_amounts(manager: BudgetManager) -> None:
    """Test NaN and Infinity raise ValueError."""

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        await manager.record_spend("user_1", float("nan"))

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        await manager.record_spend("user_1", float("inf"))

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        await manager.record_spend("user_1", float("-inf"))


@pytest.mark.asyncio
async def test_garbage_redis_url() -> None:
    """Test invalid Redis URL handling."""
    config = BudgetConfig(redis_url="notarealprotocol://bad-url")
    # redis-py's from_url validates the scheme immediately.
    # So this should raise ValueError on initialization.
    with pytest.raises(ValueError):
        BudgetManager(config)


@pytest.mark.asyncio
async def test_env_var_config_loading() -> None:
    """Test loading config from environment variables."""

    env_vars = {
        "COREASON_BUDGET_REDIS_URL": "redis://env-var-host:6379",
        "COREASON_BUDGET_DAILY_USER_LIMIT_USD": "99.99",
        "COREASON_BUDGET_DAILY_PROJECT_LIMIT_USD": "888.88",
    }

    with patch.dict(os.environ, env_vars):
        # We need to re-import or re-instantiate Config to pick up env vars
        config = BudgetConfig()

        assert config.redis_url == "redis://env-var-host:6379"
        assert config.daily_user_limit_usd == 99.99
        assert config.daily_project_limit_usd == 888.88


@pytest.mark.asyncio
async def test_mixed_optional_params(manager: BudgetManager) -> None:
    """Test providing one optional param but not the other."""
    user_id = "user_mixed"

    # Only project provided
    await manager.record_spend(user_id, 1.0, project_id="proj_A")
    # Verify project key exists
    date_str = manager.guard._get_date_str()
    proj_key = f"spend:v1:project:proj_A:{date_str}"
    assert await manager.ledger.get_usage(proj_key) == 1.0

    # Only model provided
    with patch("coreason_budget.guard.logger") as mock_logger:
        await manager.record_spend(user_id, 1.0, model="gpt-4")
        args, _ = mock_logger.info.call_args
        # project should be unknown, model should be gpt-4
        assert args[2] == "gpt-4"
        assert args[3] == "unknown"
