from unittest.mock import patch

import fakeredis.aioredis
import pytest
from redis.exceptions import ConnectionError as RedisPyConnectionError
from redis.exceptions import RedisError

from coreason_identity.models import UserContext
from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError
from coreason_budget.manager import BudgetManager


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(
        redis_url="redis://localhost",
        daily_global_limit_usd=1000000.0,
        daily_user_limit_usd=1000.0,
    )

def create_context(user_id: str) -> UserContext:
    return UserContext(
        user_id=user_id,
        email="test@example.com",
        groups=[],
        scopes=[],
        claims={}
    )


@pytest.mark.asyncio
async def test_unicode_special_char_ids(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)

        user_id = "user:name/with@special#chars & emoji 🚀"
        context = create_context(user_id)

        assert await mgr.check_availability(context, estimated_cost=10.0) is True

        await mgr.record_spend(context, 10.0)

        keys = await fake_redis.keys("*")
        matching_keys = [k for k in keys if user_id in k]
        assert len(matching_keys) > 0

        val = await fake_redis.get(matching_keys[0])
        assert float(val) == 10.0

        await mgr.close()


@pytest.mark.asyncio
async def test_large_numbers(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "whale_user"
        context = create_context(user_id)

        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(context, estimated_cost=2000.0)

        await mgr.record_spend(context, 2000.0)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        val = await fake_redis.get(keys[0])
        assert float(val) == 2000.0

        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(context, estimated_cost=1.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_redis_downtime_during_charge(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "unlucky_user"
        context = create_context(user_id)

        with patch.object(mgr._async_ledger._redis, "eval", side_effect=RedisPyConnectionError("Connection lost")):
            from redis.exceptions import RedisError

            with pytest.raises(RedisError):
                await mgr.record_spend(context, 10.0)

        await mgr.close()
