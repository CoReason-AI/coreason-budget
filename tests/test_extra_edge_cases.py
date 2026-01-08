from unittest.mock import patch

import fakeredis.aioredis
import pytest
from redis.exceptions import ConnectionError as RedisPyConnectionError

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


@pytest.mark.asyncio
async def test_unicode_special_char_ids(config: CoreasonBudgetConfig) -> None:
    """
    Verify that User IDs with special characters, unicode, and spaces work correctly.
    Redis keys should be constructed safely (or at least consistently).
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)

        # Weird user ID: "user:name/with@special#chars & emoji 🚀"
        user_id = "user:name/with@special#chars & emoji 🚀"

        # Check availability should work
        assert await mgr.check_availability(user_id, estimated_cost=10.0) is True

        # Record spend
        await mgr.record_spend(user_id, 10.0)

        # Verify key exists and value is correct
        # Note: We rely on internal _get_keys or just scan redis
        keys = await fake_redis.keys("*")
        # Ensure at least one key contains our user_id (handling encoding if any)
        # Redis-py handles unicode by encoding to utf-8 usually.
        # Our key gen: f"budget:user:{user_id}:{date_str}"
        # We expect it to match.
        matching_keys = [k for k in keys if user_id in k]
        assert len(matching_keys) > 0

        val = await fake_redis.get(matching_keys[0])
        assert float(val) == 10.0

        await mgr.close()


@pytest.mark.asyncio
async def test_large_numbers(config: CoreasonBudgetConfig) -> None:
    """
    Verify that the system handles very large costs (e.g. 1 million)
    checking against limits correctly.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "whale_user"

        # Attempt to check more than user limit (1000)
        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(user_id, estimated_cost=2000.0)

        # Record a large spend that is within global limit but exceeds user limit
        # This shouldn't happen in normal flow (check then charge), but if it does:
        # record_spend doesn't check limits, it just increments.
        # This is by design (charge what you used).
        await mgr.record_spend(user_id, 2000.0)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        val = await fake_redis.get(keys[0])
        assert float(val) == 2000.0

        # Now subsequent checks should fail
        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(user_id, estimated_cost=1.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_redis_downtime_during_charge(config: CoreasonBudgetConfig) -> None:
    """
    Verify behavior when Redis fails during `record_spend`.
    It should raise an exception so the application knows the charge failed
    (and can retry or log to a secondary system).
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "unlucky_user"

        # Patch the ledger's increment method to simulate failure
        # We need to patch the instance method on the manager's ledger
        with patch.object(mgr._async_ledger._redis, "eval", side_effect=RedisPyConnectionError("Connection lost")):
            # We expect the exception to propagate
            # The code in ledger.py catches RedisError and logs it, then re-raises.
            # So we verify it re-raises.
            from redis.exceptions import RedisError

            with pytest.raises(RedisError):
                await mgr.record_spend(user_id, 10.0)

        await mgr.close()
