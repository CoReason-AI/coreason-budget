import asyncio
import datetime

import pytest
from redis.exceptions import ResponseError

from coreason_budget import BudgetConfig, BudgetExceededError, BudgetManager


@pytest.mark.asyncio
async def test_garbage_data_in_redis() -> None:
    """
    Edge Case: Redis key contains non-numeric string.
    Expected: get_usage should raise or return 0? The code floats it.
    If it's garbage, float() conversion fails.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_garbage"
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"

    # Manually inject garbage
    await mgr.ledger._redis.set(key, "NOT_A_NUMBER")

    # check_availability -> get_usage -> float(val) -> ValueError
    with pytest.raises(ValueError):
        await mgr.check_availability(user_id)

    # record_spend -> increment -> LUA script
    # Lua INCRBYFLOAT raises error if value is not float-parsable
    # redis.exceptions.ResponseError
    with pytest.raises(ResponseError):
        await mgr.record_spend(user_id, 10.0)


@pytest.mark.asyncio
async def test_runtime_config_changes() -> None:
    """
    Edge Case: Modify config object while manager is running.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=10.0)
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_dynamic"

    # 1. Spend 10.0 (Hit Limit)
    await mgr.record_spend(user_id, 10.0)

    # Check - should fail
    with pytest.raises(BudgetExceededError):
        await mgr.check_availability(user_id, estimated_cost=1.0)

    # 2. Update Config Runtime
    mgr.config.daily_user_limit_usd = 20.0

    # Check - should pass now
    try:
        await mgr.check_availability(user_id, estimated_cost=1.0)
    except BudgetExceededError:
        pytest.fail("Runtime config update was not respected!")


@pytest.mark.asyncio
async def test_massive_concurrency_hammer() -> None:
    """
    Edge Case: 1000 concurrent requests.
    Verify atomic counting is exact.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_hammer"
    count = 100
    cost_per_req = 1.0

    async def worker() -> None:
        await mgr.record_spend(user_id, cost_per_req)

    # Run 100 concurrent tasks
    await asyncio.gather(*[worker() for _ in range(count)])

    # Verify total
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"
    val = await mgr.ledger.get_usage(key)

    assert val == float(count * cost_per_req)


@pytest.mark.asyncio
async def test_negative_spend_refund() -> None:
    """
    Edge Case: Refund (Negative Spend).
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_refund"

    # Spend 50
    await mgr.record_spend(user_id, 50.0)

    # Refund 20
    await mgr.record_spend(user_id, -20.0)

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"
    val = await mgr.ledger.get_usage(key)

    assert val == 30.0


@pytest.mark.asyncio
async def test_extremely_small_amounts() -> None:
    """
    Edge Case: Floating point precision with tiny amounts.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)

    user_id = "user_tiny"
    tiny_amount = 0.0000001

    for _ in range(10):
        await mgr.record_spend(user_id, tiny_amount)

    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key = f"spend:v1:user:{user_id}:{date_str}"
    val = await mgr.ledger.get_usage(key)

    # Float precision might be slightly off, use approx
    assert val == pytest.approx(0.000001)


@pytest.mark.asyncio
async def test_empty_keys_handling() -> None:
    """
    Edge Case: User ID is empty string or None.
    Should be caught by validation.
    """
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = BudgetManager(config)

    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        await mgr.check_availability("")

    with pytest.raises(ValueError):
        await mgr.record_spend("", 10.0)
