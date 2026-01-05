import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from coreason_budget import BudgetConfig, BudgetExceededError, BudgetManager
from coreason_budget.ledger import RedisLedger


@pytest.mark.asyncio
async def test_concurrency_race_condition(manager: BudgetManager) -> None:
    user_id = "user_race"

    async def task() -> bool:
        await manager.check_availability(user_id, estimated_cost=1.0)
        return True

    results = await asyncio.gather(*(task() for _ in range(20)), return_exceptions=True)
    assert len([r for r in results if r is True]) == 20
    for _ in range(20):
        await manager.record_spend(user_id, 1.0, project_id="proj_race", model="gpt-4")
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=1.0)


@pytest.mark.asyncio
async def test_hierarchy_project_limit_hit_first() -> None:
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=100.0, daily_project_limit_usd=10.0)
    mgr = BudgetManager(config)
    from fakeredis.aioredis import FakeRedis

    mgr.ledger._redis = FakeRedis(decode_responses=True)
    user_id = "user_h"
    project_id = "proj_h"
    await mgr.record_spend(user_id, 10.0, project_id=project_id, model="gpt-4")
    with pytest.raises(BudgetExceededError):
        await mgr.check_availability(user_id, project_id=project_id, estimated_cost=1.0)
    await mgr.close()


@pytest.mark.asyncio
async def test_redis_ledger_error_handling(manager: BudgetManager) -> None:
    await manager.ledger.connect()
    # Use type: ignore because assignment to method of mock/object might be flagged or handled differently
    # actually patch.object is cleaner
    with patch.object(manager.ledger._redis, "get", side_effect=RedisError("Get Failed")):
        with pytest.raises(RedisError):
            await manager.ledger.get_usage("some_key")
    with patch.object(manager.ledger._redis, "eval", side_effect=RedisError("Eval Failed")):
        with pytest.raises(RedisError):
            await manager.ledger.increment("some_key", 1.0)


@pytest.mark.asyncio
async def test_redis_connect_failure_ping() -> None:
    # Cover lines 32-33: ping fails
    # Need to patch from_url BEFORE creating ledger, because it is called in __init__
    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock(side_effect=RedisError("Ping Failed"))

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        ledger = RedisLedger("redis://localhost:6379")
        with pytest.raises(RedisConnectionError):
            await ledger.connect()


@pytest.mark.asyncio
async def test_ledger_close_coverage() -> None:
    # Cover line 48: close when _redis is NOT None
    mock_redis = MagicMock()
    mock_redis.aclose = AsyncMock()

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        ledger = RedisLedger("redis://localhost:6379")
        await ledger.close()
        mock_redis.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_zero_and_negative_spend(manager: BudgetManager) -> None:
    user_id = "user_free"
    await manager.record_spend(user_id, 0.0, project_id="proj_free", model="gpt-4")
    await manager.check_availability(user_id)
    await manager.record_spend(user_id, -5.0, project_id="proj_free", model="gpt-4")
    await manager.record_spend(user_id, 10.0, project_id="proj_free", model="gpt-4")
    await manager.check_availability(user_id, estimated_cost=4.0)
    await manager.record_spend(user_id, 5.0, project_id="proj_free", model="gpt-4")
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, estimated_cost=0.1)


@pytest.mark.asyncio
async def test_pricing_failure(manager: BudgetManager) -> None:
    with patch("coreason_budget.pricing.litellm.completion_cost", side_effect=Exception("API Error")):
        with pytest.raises(Exception, match="API Error"):
            manager.pricing.calculate("bad-model", 10, 10)


@pytest.mark.asyncio
async def test_pricing_overrides() -> None:
    from coreason_budget.config import ModelPrice

    config = BudgetConfig(
        daily_limit_usd=100.0,
        model_price_overrides={"custom-model": ModelPrice(input_cost_per_token=0.01, output_cost_per_token=0.02)},
    )
    mgr = BudgetManager(config)
    cost = mgr.pricing.calculate("custom-model", 10, 10)
    assert pytest.approx(cost) == 0.3
    await mgr.close()
