from unittest.mock import patch

import pytest

from coreason_budget import BudgetExceededError, BudgetManager
from coreason_budget.config import ModelPrice


@pytest.mark.asyncio
async def test_limit_precedence(manager: BudgetManager) -> None:
    """
    Verify that limits are checked in Global -> Project -> User order.
    If multiple limits are exceeded, the Global one should be reported first
    (or at least, the system should stop at the highest level breach).
    """
    user_id = "user_prec"
    project_id = "proj_prec"

    # Configure limits: Global=5000, Project=500, User=10
    # We want to simulate a state where ALL are exceeded.
    # To do this cleanly, we can mock the ledger to return values exceeding all limits.

    # Global Limit: 5000 -> Mock usage 6000
    # Project Limit: 500 -> Mock usage 600
    # User Limit: 10 -> Mock usage 20

    async def mock_get_usage(key: str) -> float:
        if "global" in key:
            return 6000.0
        if "project" in key:
            return 600.0
        if "user" in key:
            return 20.0
        return 0.0

    with patch.object(manager.ledger, "get_usage", side_effect=mock_get_usage):
        # When we check availability, it should raise BudgetExceededError.
        # We check the message to see WHICH limit triggered it.
        with pytest.raises(BudgetExceededError) as exc_info:
            await manager.check_availability(user_id, project_id=project_id, estimated_cost=1.0)

        # The message should mention "Global"
        assert "Global" in str(exc_info.value)
        assert "5000.0" in str(exc_info.value)

    # Now let's test Project vs User precedence (Global is fine)
    async def mock_get_usage_proj_user(key: str) -> float:
        if "global" in key:
            return 100.0  # Under limit
        if "project" in key:
            return 600.0  # Over limit
        if "user" in key:
            return 20.0  # Over limit
        return 0.0

    with patch.object(manager.ledger, "get_usage", side_effect=mock_get_usage_proj_user):
        with pytest.raises(BudgetExceededError) as exc_info:
            await manager.check_availability(user_id, project_id=project_id, estimated_cost=1.0)

        assert "Project" in str(exc_info.value)
        assert "500.0" in str(exc_info.value)


@pytest.mark.asyncio
async def test_runtime_config_updates(manager: BudgetManager) -> None:
    """
    Verify that updates to the config object are reflected immediately.
    """
    user_id = "user_config_test"

    # 1. Set a high limit initially
    manager.config.daily_user_limit_usd = 1000.0

    # Spend 50
    await manager.record_spend(user_id, 50.0)

    # Check should pass (50 < 1000)
    await manager.check_availability(user_id, estimated_cost=10.0)

    # 2. Update config at runtime to lower limit
    manager.config.daily_user_limit_usd = 40.0

    # Check should now fail (50 > 40)
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=1.0)

    # 3. Update Global limit
    manager.config.daily_global_limit_usd = 10.0
    with pytest.raises(BudgetExceededError) as exc_info:
        # Even if user limit was raised back, Global would block
        manager.config.daily_user_limit_usd = 10000.0
        await manager.check_availability(user_id, estimated_cost=1.0)
    assert "Global" in str(exc_info.value)


@pytest.mark.asyncio
async def test_free_model_override(manager: BudgetManager) -> None:
    """
    Verify that models can be configured to be free (cost = 0).
    """
    model_name = "free-gpt"

    # Configure override
    manager.config.model_price_overrides[model_name] = ModelPrice(input_cost_per_token=0.0, output_cost_per_token=0.0)

    # Calculate cost
    cost = manager.pricing.calculate(model_name, input_tokens=1000, output_tokens=1000)
    assert cost == 0.0

    # Record spend
    user_id = "user_free_tier"
    await manager.record_spend(user_id, cost, model=model_name)

    # Verify usage did not increase (or increased by 0)
    # We need to access the key.
    # Since we can't easily guess the exact key without helper (it depends on date),
    # let's just use check_availability with a limit of 0.0.
    # If usage is 0.0, check(limit=0.0) might pass or fail depending on >= logic.
    # Logic is: if used >= limit. 0 >= 0 is True. So it fails if limit is exactly 0 and we used 0.

    # Let's set limit to small positive
    manager.config.daily_user_limit_usd = 0.1
    await manager.check_availability(user_id, estimated_cost=0.05)

    # Now record a REAL spend
    await manager.record_spend(user_id, 1.0)

    # Now it should fail
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=0.05)
