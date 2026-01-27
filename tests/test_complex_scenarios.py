import asyncio
from unittest.mock import patch

import fakeredis.aioredis
import pytest
from datetime import datetime

from coreason_identity.models import UserContext
from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError
from coreason_budget.manager import BudgetManager


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(
        redis_url="redis://localhost", daily_user_limit_usd=100.0, daily_global_limit_usd=1000.0
    )

def create_context(user_id: str) -> UserContext:
    return UserContext(
        user_id=user_id,
        email=f"{user_id}@example.com",
        groups=[],
        scopes=[],
        claims={}
    )


@pytest.mark.asyncio
async def test_concurrency_race_condition(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "concurrent_user"
        context = create_context(user_id)

        tasks = [mgr.record_spend(context, 1.0) for _ in range(100)]
        await asyncio.gather(*tasks)

        keys = await fake_redis.keys("*")
        user_key = next(k for k in keys if f"user:{user_id}" in k)

        val = await fake_redis.get(user_key)
        assert float(val) == 100.0

        await mgr.close()


@pytest.mark.asyncio
async def test_refund_logic(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "refund_user"
        context = create_context(user_id)

        await mgr.record_spend(context, 50.0)
        await mgr.record_spend(context, -20.0)

        assert await mgr.check_availability(context, estimated_cost=60.0) is True

        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(context, estimated_cost=80.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_floating_point_precision(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "float_user"
        context = create_context(user_id)

        for _ in range(10):
            await mgr.record_spend(context, 0.0000001)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        val = await fake_redis.get(keys[0])

        assert float(val) == pytest.approx(0.000001)

        await mgr.close()


@pytest.mark.asyncio
async def test_zero_cost(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "zero_user"
        context = create_context(user_id)

        await mgr.record_spend(context, 0.0)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        assert len(keys) == 1
        val = await fake_redis.get(keys[0])
        assert float(val) == 0.0

        await mgr.close()


@pytest.mark.asyncio
async def test_ttl_near_midnight(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    mock_now = datetime(2023, 10, 27, 23, 59, 0)

    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
        patch("coreason_budget.guard.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value = mock_now

        mgr = BudgetManager(config)
        user_id = "midnight_user"
        context = create_context(user_id)

        await mgr.record_spend(context, 10.0)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        ttl = await fake_redis.ttl(keys[0])

        assert 58 <= ttl <= 62

        await mgr.close()
