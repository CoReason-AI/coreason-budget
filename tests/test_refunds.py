# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import pytest

from coreason_budget import BudgetManager


@pytest.mark.asyncio
async def test_refund_logic(manager: BudgetManager) -> None:
    """Test that negative amounts (refunds) correctly decrease the spend."""
    user_id = "user_refund"
    project_id = "proj_refund"
    model = "gpt-refund"

    # 1. Spend some money (e.g., $5)
    await manager.record_spend(user_id, 5.0, project_id=project_id, model=model)

    # Check current usage
    # We can inspect via guard/ledger or infer via check_availability behavior.
    # Since check_availability only raises if limit exceeded, let's peek at ledger directly for verification.
    # The key format is internal but we can reconstruct it or use manager.guard.

    # Let's trust the public API: if we spend $5, then refund $2, we should have $3 usage.
    # If limit is $10.
    # If we refund $2, usage is $3.
    # If we check availability with estimated_cost=$7, $3+$7 = $10 (Limit), so it should pass (or fail if > vs >=).
    # Logic: used >= limit or used + est > limit.
    # $3 + $7 = $10. $10 > $10 is False. So pass.
    # If we hadn't refunded, $5 + $7 = $12 > $10. Fail.

    # Refund $2
    await manager.record_spend(user_id, -2.0, project_id=project_id, model=model)

    # Try to spend $7 (Total $10) -> Should pass
    await manager.check_availability(user_id, estimated_cost=7.0)

    # If we hadn't refunded, usage was $5. Check $7 -> $12 > $10 -> Fail.
    # Let's verify this negative case to be sure our test logic is sound.
    # Refund the $7 we just "checked" (checking doesn't spend, so no need to refund check).

    # Reset usage manually or just use another user for control?
    # Let's use another user for control.
    user_control = "user_control"
    await manager.record_spend(user_control, 5.0, project_id=project_id, model=model)
    # Check $7 -> $12 > $10 -> Should fail
    from coreason_budget.guard import BudgetExceededError

    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_control, estimated_cost=7.0)

    # Conclusion: Refund worked for user_refund.


@pytest.mark.asyncio
async def test_refund_below_zero(manager: BudgetManager) -> None:
    """Test that usage can go below zero if refunded more than spent (technically possible in Redis)."""
    # This behavior might be desirable or not, but usually allowed for simple counters.
    user_id = "user_lucky"
    project_id = "p"
    model = "m"

    await manager.record_spend(user_id, -5.0, project_id=project_id, model=model)

    # Usage is -5.
    # Limit is 10.
    # check with est 14. -5 + 14 = 9 < 10. Should pass.
    await manager.check_availability(user_id, estimated_cost=14.0)

    # If usage was 0, 14 > 10, would fail.
