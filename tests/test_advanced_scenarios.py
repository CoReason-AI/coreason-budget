import asyncio
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import RedisError

from coreason_budget import BudgetManager


@pytest.mark.asyncio
async def test_partial_update_failure(manager: BudgetManager) -> None:
    """
    Test scenario where updating multiple keys (Global, Project, User) fails halfway.
    Current implementation loops sequentially. If one fails, subsequent ones might not run,
    and previous ones remain committed (no rollback).
    """
    user_id = "user_partial"
    project_id = "proj_partial"
    amount = 10.0

    # The order in guard.py is: Global, then Project, then User.
    # We want to fail the Project update (2nd one) and see what happens.

    # We need to mock ledger.increment to work for the first call, fail for the second.
    # Since we can't easily mock individual calls to the same method with different side effects
    # based on arguments without a complex side_effect function, we'll do exactly that.

    original_increment = manager.ledger.increment

    async def side_effect(key: str, amt: float, ttl: Optional[int] = None) -> float:
        if "project" in key:
            raise RedisError("Simulated Partial Failure")
        return await original_increment(key, amt, ttl)

    with patch.object(manager.ledger, "increment", side_effect=side_effect):
        with pytest.raises(RedisError, match="Simulated Partial Failure"):
            await manager.record_spend(user_id, amount, project_id=project_id, model="gpt-4")

    # Verify State:
    date_str = manager.guard._get_date_str()

    # Global should have incremented (First)
    global_key = f"spend:v1:global:{date_str}"
    assert await manager.ledger.get_usage(global_key) == amount

    # Project should NOT have incremented (Failed)
    project_key = f"spend:v1:project:{project_id}:{date_str}"
    assert await manager.ledger.get_usage(project_key) == 0.0

    # User should NOT have incremented (Skipped due to exception)
    user_key = f"spend:v1:user:{user_id}:{date_str}"
    assert await manager.ledger.get_usage(user_key) == 0.0


@pytest.mark.asyncio
async def test_user_id_with_colons(manager: BudgetManager) -> None:
    """
    Test that user_ids with colons don't break key construction or Redis.
    """
    user_id = "user:name:complex:123"
    amount = 5.0

    await manager.record_spend(user_id, amount)

    date_str = manager.guard._get_date_str()
    # Expected key: spend:v1:user:user:name:complex:123:{date}
    expected_key = f"spend:v1:user:{user_id}:{date_str}"

    usage = await manager.ledger.get_usage(expected_key)
    assert usage == 5.0

    # Verify check availability works
    await manager.check_availability(user_id, estimated_cost=1.0)


@pytest.mark.asyncio
async def test_negative_ttl_behavior(manager: BudgetManager) -> None:
    """
    Test what happens if TTL calculation returns a negative number or zero.
    We verify that our code clamps it to 1, preventing key deletion.
    """
    user_id = "user_neg_ttl"
    amount = 10.0

    # Let's just call `_get_ttl_seconds` and ensure it is >= 1.
    val = manager.guard._get_ttl_seconds()
    assert val >= 1

    # To really test the fix, we can mock `total_seconds` to return -5.
    # The method calls `(midnight - now).total_seconds()`.
    # We can mock the return value of total_seconds.

    with patch("coreason_budget.guard.datetime") as mock_dt:
        mock_now = MagicMock()
        mock_dt.datetime.now.return_value = mock_now

        # We need the subtraction to return a timedelta whose .total_seconds() is -5
        mock_delta = MagicMock()
        mock_delta.total_seconds.return_value = -5.0

        mock_midnight = MagicMock()
        mock_midnight.__sub__.return_value = mock_delta  # midnight - now

        # setup datetime(...) constructor to return mock_midnight
        mock_dt.datetime.return_value = mock_midnight

        # Call the method
        ttl = manager.guard._get_ttl_seconds()

        # It should be clamped to 1
        assert ttl == 1, f"Expected clamped TTL of 1, got {ttl}"

    # Now verify that with TTL=1, the key is NOT deleted immediately (it lives for 1s).
    # We can use fakeredis to check.

    await manager.record_spend(user_id, amount)
    # Since we didn't force negative TTL here (we only tested the clamp logic above),
    # this just confirms standard behavior, which is fine.
    # To connect the dots: The logic above proves guard returns 1 even if calc is -5.
    # And we know from previous failure that -5 deletes key.
    # So 1 should save it.

    date_str = manager.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"
    usage = await manager.ledger.get_usage(key)
    assert usage == 10.0


@pytest.mark.asyncio
async def test_high_concurrency_load(manager: BudgetManager) -> None:
    """
    Simulate high concurrency (e.g. 100 requests) to ensure stability.
    """
    user_id = "user_concurrent_high"

    # 100 concurrent record_spend calls
    n = 100
    amount = 0.1

    async def spend() -> None:
        await manager.record_spend(user_id, amount)

    await asyncio.gather(*(spend() for _ in range(n)))

    date_str = manager.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"

    usage = await manager.ledger.get_usage(key)
    # 100 * 0.1 = 10.0
    assert pytest.approx(usage) == 10.0
