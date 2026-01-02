# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from unittest.mock import patch

import pytest

from coreason_budget import BudgetExceededError, BudgetManager


@pytest.mark.asyncio
async def test_end_to_end_flow(manager: BudgetManager) -> None:
    """Test the complete check -> run -> charge flow."""
    user_id = "user_e2e"

    # 1. Pre-flight check (should pass)
    await manager.check_availability(user_id)

    # 2. Calculate cost
    # Mock pricing for predictability
    with patch("coreason_budget.pricing.litellm.completion_cost", return_value=0.05):
        cost = manager.pricing.calculate("gpt-4", 100, 100)
    assert cost == 0.05

    # 3. Record spend
    await manager.record_spend(user_id, cost, model="gpt-4")

    # 4. Check availability again (should pass)
    await manager.check_availability(user_id)


@pytest.mark.asyncio
async def test_budget_exceeded_flow(manager: BudgetManager) -> None:
    """Test flow where budget is exceeded."""
    user_id = "user_broke"
    limit = manager.config.daily_user_limit_usd  # 10.0

    # Record enough spend to reach limit
    await manager.record_spend(user_id, limit, model="gpt-4")

    # Verify check fails
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id)


@pytest.mark.asyncio
async def test_check_availability_estimation_pass_through(manager: BudgetManager) -> None:
    """Test that estimated_cost is passed through to the guard."""
    user_id = "user_pass_through"
    # Limit 10.0

    # 1. Spend 8.0
    await manager.record_spend(user_id, 8.0)

    # 2. Check with 3.0 -> should fail (11.0 > 10.0)
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=3.0)


@pytest.mark.asyncio
async def test_pricing_integration(manager: BudgetManager) -> None:
    """Test pricing engine access."""
    assert manager.pricing is not None
    # We mocked litellm in unit tests, here we might want to check it works or mock again.
    # Since we don't have API keys, real calls fail.
    # So we mock.
    with patch("coreason_budget.pricing.litellm.completion_cost", return_value=1.0):
        cost = manager.pricing.calculate("m", 1, 1)
        assert cost == 1.0
