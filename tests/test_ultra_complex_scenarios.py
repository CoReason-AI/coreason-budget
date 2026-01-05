import datetime
from unittest.mock import MagicMock, patch

import pytest

from coreason_budget import BudgetConfig, BudgetManager


@pytest.mark.asyncio
async def test_partial_failure_consistency(manager: BudgetManager) -> None:
    """
    Test scenario: record_spend updates Global, Project, and User keys.
    If Global succeeds but Project fails, what happens?
    The current implementation loops sequentially.
    """
    user_id = "user_partial"
    project_id = "proj_partial"

    # We mock ledger.increment to succeed for first call, fail for second.
    # The order in BudgetGuard._get_keys_and_limits is Global, Project, User.

    original_increment = manager.ledger.increment

    async def side_effect(key: str, amount: float, ttl: int | None = None) -> float:
        if "global" in key:
            return await original_increment(key, amount, ttl)
        if "project" in key:
            raise RuntimeError("Redis Failed Halfway")
        return await original_increment(key, amount, ttl)

    with patch.object(manager.ledger, "increment", side_effect=side_effect):
        with pytest.raises(RuntimeError, match="Redis Failed Halfway"):
            await manager.record_spend(user_id, 1.0, project_id=project_id)

    # Verify State:
    # Global should be incremented (1.0)
    # Project should NOT be incremented (0.0)
    # User should NOT be incremented (0.0) - because loop aborted

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    global_key = f"spend:v1:global:{date_str}"
    project_key = f"spend:v1:project:{project_id}:{date_str}"
    user_key = f"spend:v1:user:{user_id}:{date_str}"

    global_usage = await manager.ledger.get_usage(global_key)
    project_usage = await manager.ledger.get_usage(project_key)
    user_usage = await manager.ledger.get_usage(user_key)

    assert global_usage == 1.0
    assert project_usage == 0.0
    assert user_usage == 0.0
    # This confirms "Partial Failure" behavior exists.
    # While not ideal, it is "Fail Closed" in the sense that budget IS consumed (Global),
    # preventing overspending globally, but potentially allowing user/project overspending
    # if we only checked the user/project key later.
    # However, since check_availability checks ALL keys, and Global is incremented,
    # the Global limit will be enforced correctly.
    # The user/project limits might be slightly "under-counted" relative to global.


@pytest.mark.asyncio
async def test_ttl_first_write_persistence() -> None:
    """
    Verify that TTL is set on first write and NOT reset on subsequent writes.
    We need to mock Redis commands carefully or inspect calls.
    Using fakeredis, we can inspect TTL directly.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_ttl"
    key = f"spend:v1:user:{user_id}:{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')}"

    # First write: TTL should be set.
    # We patch _get_ttl_seconds to return a fixed value so we can check it.
    fixed_ttl = 3600
    with patch.object(mgr.guard, "_get_ttl_seconds", return_value=fixed_ttl):
        await mgr.record_spend(user_id, 10.0)

    # Check TTL in redis
    actual_ttl = await mgr.ledger._redis.ttl(key)
    # In fakeredis, TTL might be slightly less than set value immediately, or exactly.
    assert actual_ttl <= fixed_ttl
    assert actual_ttl > fixed_ttl - 5  # Allow small delay

    # Second write: Simulate later time where calculated TTL would be smaller.
    # But we want to ensure the EXISTING TTL is preserved.
    # To test this, we pass a DIFFERENT TTL to increment.
    # If the script uses the new TTL, actual_ttl will change.
    # If the script respects existing TTL, it will stay ~3600.

    new_smaller_ttl = 100
    with patch.object(mgr.guard, "_get_ttl_seconds", return_value=new_smaller_ttl):
        await mgr.record_spend(user_id, 10.0)

    actual_ttl_after = await mgr.ledger._redis.ttl(key)

    # It should still be close to 3600, NOT 100.
    assert actual_ttl_after > 3000
    assert actual_ttl_after <= 3600


@pytest.mark.asyncio
async def test_very_large_input_tokens() -> None:
    """
    Test very large token counts.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    # Mock pricing to just multiply
    # We can't use real pricing for 1B tokens without credentials likely, or it's fine.
    # Let's mock it to return a huge number.
    mgr.pricing.calculate = MagicMock(return_value=1_000_000.0)

    user_id = "user_huge"
    # Pre-flight check should fail against 10.0 limit
    from coreason_budget.guard import BudgetExceededError

    with pytest.raises(BudgetExceededError):
        await mgr.check_availability(user_id, estimated_cost=1_000_000.0)

    # Record spend (maybe post-flight without pre-flight check)
    await mgr.record_spend(user_id, 1_000_000.0)

    usage = await mgr.ledger.get_usage(
        f"spend:v1:user:{user_id}:{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')}"
    )
    assert usage == 1_000_000.0


@pytest.mark.asyncio
async def test_clock_skew_simulation() -> None:
    """
    Test behavior when machine time shifts.
    If time jumps forward, we write to new key.
    If time jumps backward, we write to old key.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_time_travel"

    # Time 1: Today
    with patch.object(mgr.guard, "_get_date_str", return_value="2025-01-01"):
        await mgr.record_spend(user_id, 10.0)
        assert await mgr.ledger.get_usage("spend:v1:user:user_time_travel:2025-01-01") == 10.0

    # Time 2: Tomorrow (Clock Jump Forward)
    with patch.object(mgr.guard, "_get_date_str", return_value="2025-01-02"):
        await mgr.record_spend(user_id, 5.0)
        assert await mgr.ledger.get_usage("spend:v1:user:user_time_travel:2025-01-02") == 5.0

    # Time 3: Back to Today (Clock Jump Backward)
    with patch.object(mgr.guard, "_get_date_str", return_value="2025-01-01"):
        await mgr.record_spend(user_id, 5.0)
        # Should accumulate on the old key
        assert await mgr.ledger.get_usage("spend:v1:user:user_time_travel:2025-01-01") == 15.0
