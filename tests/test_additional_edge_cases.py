import datetime
from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from coreason_budget import BudgetConfig, BudgetExceededError, BudgetManager


@pytest.mark.asyncio
async def test_small_precision_costs(manager: BudgetManager) -> None:
    """Test extremely small cost values are handled correctly."""
    user_id = "user_precision"
    tiny_cost = 0.0000001

    # Record a tiny spend
    await manager.record_spend(user_id, tiny_cost, project_id="proj_precision", model="gpt-4")

    # Check if it was recorded
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"
    usage = await manager.ledger.get_usage(key)

    assert usage > 0.0
    assert pytest.approx(usage) == tiny_cost


@pytest.mark.asyncio
async def test_negative_spend_refund(manager: BudgetManager) -> None:
    """Test negative spend (refunds) correctly reduces usage."""
    user_id = "user_refund"
    initial_spend = 5.0
    refund = -2.0

    await manager.record_spend(user_id, initial_spend, project_id="proj_refund", model="gpt-4")

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"

    usage_before = await manager.ledger.get_usage(key)
    assert pytest.approx(usage_before) == 5.0

    await manager.record_spend(user_id, refund, project_id="proj_refund", model="gpt-4")

    usage_after = await manager.ledger.get_usage(key)
    assert pytest.approx(usage_after) == 3.0


@pytest.mark.asyncio
async def test_large_single_transaction_check(manager: BudgetManager) -> None:
    """Test a single transaction larger than the daily limit."""
    user_id = "user_whale"
    huge_cost = 1000.0

    # Pre-flight should block it
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=huge_cost)


@pytest.mark.asyncio
async def test_large_single_transaction_record(manager: BudgetManager) -> None:
    """
    Test recording a spend larger than limit.
    This can happen if pre-flight was skipped or estimate was wrong.
    It should still record it, even if it breaks the limit for future requests.
    """
    user_id = "user_overshoot"
    huge_cost = 20.0  # Limit is 10.0

    await manager.record_spend(user_id, huge_cost, project_id="proj_overshoot", model="gpt-4")

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"
    usage = await manager.ledger.get_usage(key)

    assert usage == 20.0

    # Next check should definitely fail
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=0.1)


@pytest.mark.asyncio
async def test_midnight_rollover() -> None:
    """
    Test that keys change when date changes (rollover).
    """
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=10.0)
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_midnight"

    # Day 1: 2023-10-27
    with patch.object(mgr.guard, "_get_date_str", return_value="2023-10-27"):
        await mgr.record_spend(user_id, 5.0, project_id="proj_mid", model="gpt-4")

        key_day1 = "spend:v1:user:user_midnight:2023-10-27"
        usage = await mgr.ledger.get_usage(key_day1)
        assert usage == 5.0

        # Check availability should pass
        await mgr.check_availability(user_id, estimated_cost=1.0)

    # Day 2: 2023-10-28
    with patch.object(mgr.guard, "_get_date_str", return_value="2023-10-28"):
        # Previous spend should not count against today
        # Check availability should see 0 usage for new key

        # We assume new key is empty
        key_day2 = "spend:v1:user:user_midnight:2023-10-28"
        usage_day2 = await mgr.ledger.get_usage(key_day2)
        assert usage_day2 == 0.0

        # Should allow full 10.0 spend
        await mgr.check_availability(user_id, estimated_cost=10.0)
        await mgr.record_spend(user_id, 10.0, project_id="proj_mid", model="gpt-4")

        assert await mgr.ledger.get_usage(key_day2) == 10.0

    await mgr.close()


@pytest.mark.asyncio
async def test_empty_user_id() -> None:
    """Test behavior with empty user_id."""
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    await mgr.record_spend("", 1.0, project_id="proj_empty", model="gpt-4")
    await mgr.close()


@pytest.mark.asyncio
async def test_redis_fail_closed(manager: BudgetManager) -> None:
    """
    Test Fail Closed policy: If Redis is down, check_availability must raise exception.
    """
    # Simulate connection failure on get_usage
    with patch.object(manager.ledger, "get_usage", side_effect=RedisConnectionError("Redis Down")):
        with pytest.raises(RedisConnectionError):
            await manager.check_availability("user_fail_closed", estimated_cost=1.0)
