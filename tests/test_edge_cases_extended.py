import asyncio
from unittest.mock import patch

import pytest

from coreason_budget import BudgetConfig, BudgetExceededError, BudgetManager


@pytest.mark.asyncio
async def test_simultaneous_check_and_spend(manager: BudgetManager) -> None:
    """
    Test scenario: Multiple checks and spends happening at the exact same time.
    Validates race conditions where checks pass before spends are recorded.
    """
    user_id = "user_concurrent_mixed"
    # User limit is small ($10)
    # We will launch 20 tasks: 10 checks ($1.0 est) and 10 spends ($1.0 actual)
    # Total potential spend = 20.0 (exceeds 10.0)
    # Some should fail.

    async def do_check() -> str:
        try:
            await manager.check_availability(user_id, estimated_cost=1.1)
            return "ok"
        except BudgetExceededError:
            return "exceeded"

    async def do_spend() -> str:
        await manager.record_spend(user_id, 1.0)
        return "spent"

    # Interleave them
    tasks = []
    for _ in range(10):
        tasks.append(do_spend())
        tasks.append(do_check())

    # Shuffle or just run (asyncio scheduler will interleave)
    await asyncio.gather(*tasks)

    # We expect some "exceeded" eventually.
    # Total spend recorded will be 10 * 1.0 = 10.0.
    # Checks might pass if they run before spends.
    # At end, used = 10.0.
    # Final check should definitely fail.
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=0.1)

    usage = await manager.ledger.get_usage(f"spend:v1:user:{user_id}:{manager.guard._get_date_str()}")
    assert pytest.approx(usage) == 10.0


@pytest.mark.asyncio
async def test_precision_large_numbers(manager: BudgetManager) -> None:
    """Test very large numbers to ensure no overflow/precision loss that affects logic."""
    user_id = "user_whale"
    huge_amount = 1e15  # 1 Quadrillion

    # Needs a config with huge limit
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=1e20)
    mgr = BudgetManager(config)
    # Patch ledger to use fake redis from fixture if possible, or new one
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    await mgr.record_spend(user_id, huge_amount)
    usage = await mgr.ledger.get_usage(f"spend:v1:user:{user_id}:{mgr.guard._get_date_str()}")
    assert usage == huge_amount

    # Add small amount
    await mgr.record_spend(user_id, 10.50)
    usage = await mgr.ledger.get_usage(f"spend:v1:user:{user_id}:{mgr.guard._get_date_str()}")
    assert usage == huge_amount + 10.50

    await mgr.close()


@pytest.mark.asyncio
async def test_precision_tiny_numbers(manager: BudgetManager) -> None:
    """Test very small numbers (sub-cent) accumulation."""
    user_id = "user_micro"
    tiny_amount = 0.0000001
    count = 10000

    # 10000 * 1e-7 = 1e-3 = 0.001

    for _ in range(count):
        await manager.record_spend(user_id, tiny_amount)

    usage = await manager.ledger.get_usage(f"spend:v1:user:{user_id}:{manager.guard._get_date_str()}")
    assert pytest.approx(usage, rel=1e-6) == 0.001


@pytest.mark.asyncio
async def test_date_boundary_transition(manager: BudgetManager) -> None:
    """
    Test that keys change when the date changes.
    We mock datetime to simulate crossing midnight.
    """
    user_id = "user_insomniac"

    # Actually, simpler way: patch BudgetGuard._get_date_str

    with patch.object(manager.guard, "_get_date_str", return_value="2023-10-27"):
        await manager.record_spend(user_id, 5.0)

    # Verify Day 1 Key
    usage_d1 = await manager.ledger.get_usage("spend:v1:user:user_insomniac:2023-10-27")
    assert usage_d1 == 5.0

    # Day 2 (Midnight passed)
    with patch.object(manager.guard, "_get_date_str", return_value="2023-10-28"):
        await manager.record_spend(user_id, 3.0)

    # Verify Day 2 Key
    usage_d2 = await manager.ledger.get_usage("spend:v1:user:user_insomniac:2023-10-28")
    assert usage_d2 == 3.0

    # Verify Day 1 Key is unchanged
    usage_d1_again = await manager.ledger.get_usage("spend:v1:user:user_insomniac:2023-10-27")
    assert usage_d1_again == 5.0


@pytest.mark.asyncio
async def test_extremely_long_user_id(manager: BudgetManager) -> None:
    """Test that Redis handles very long keys gracefully."""
    # Redis key limit is huge (512MB), but let's test a reasonably long one (e.g. 10KB)
    long_id = "u" * 10000
    await manager.record_spend(long_id, 1.0)

    date_str = manager.guard._get_date_str()
    usage = await manager.ledger.get_usage(f"spend:v1:user:{long_id}:{date_str}")
    assert usage == 1.0


@pytest.mark.asyncio
async def test_unicode_user_id(manager: BudgetManager) -> None:
    """Test user_id with unicode characters (emojis, etc)."""
    user_id = "user_🚀_ñame"
    await manager.record_spend(user_id, 2.5)

    date_str = manager.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"

    usage = await manager.ledger.get_usage(key)
    assert usage == 2.5

    # Ensure checking works
    await manager.check_availability(user_id)


@pytest.mark.asyncio
async def test_redis_timeout_during_spend(manager: BudgetManager) -> None:
    """
    Simulate a Redis timeout during the INCRBYFLOAT operation.
    It should raise the RedisConnectionError (mapped from RedisError or direct).
    """
    from redis.exceptions import TimeoutError

    with patch.object(manager.ledger._redis, "eval", side_effect=TimeoutError("Timeout")):
        with pytest.raises(TimeoutError):  # Or RedisError
            await manager.record_spend("user_timeout", 1.0)
