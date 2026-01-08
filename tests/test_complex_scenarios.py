import asyncio
from unittest.mock import patch

import fakeredis.aioredis
import pytest

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError
from coreason_budget.manager import BudgetManager


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(
        redis_url="redis://localhost", daily_user_limit_usd=100.0, daily_global_limit_usd=1000.0
    )


@pytest.mark.asyncio
async def test_concurrency_race_condition(config: CoreasonBudgetConfig) -> None:
    """
    Simulate multiple concurrent requests to verify atomic increments.
    If 100 requests of $1.0 happen at once, total usage should be $100.0.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "concurrent_user"

        # 100 concurrent requests of $1.0
        tasks = [mgr.record_spend(user_id, 1.0) for _ in range(100)]
        await asyncio.gather(*tasks)

        # Check usage
        # We need to construct the key manually or use mgr.guard._get_keys but _get_keys is internal.
        # However, we can use mgr.check_availability to check usage indirectly?
        # No, check just returns True/False.
        # We can inspect the fake_redis directly.

        # Determine the key (requires knowing implementation detail or exposing a helper)
        # Or we can rely on `mgr._async_ledger.get_usage` if we knew the key.
        # Let's peek at the keys in redis
        keys = await fake_redis.keys("*")
        # Find the user key
        user_key = next(k for k in keys if f"user:{user_id}" in k)

        val = await fake_redis.get(user_key)
        assert float(val) == 100.0

        await mgr.close()


@pytest.mark.asyncio
async def test_refund_logic(config: CoreasonBudgetConfig) -> None:
    """
    Verify that negative amounts reduce the usage.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "refund_user"

        # Spend 50
        await mgr.record_spend(user_id, 50.0)

        # Refund 20
        await mgr.record_spend(user_id, -20.0)

        # Check usage via checking if we can spend another 60 (limit 100)
        # Used: 50 - 20 = 30. Remaining: 70.
        # Spend 60 -> Should pass.
        assert await mgr.check_availability(user_id, estimated_cost=60.0) is True

        # Spend 80 -> Should fail (30 + 80 = 110 > 100)
        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(user_id, estimated_cost=80.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_floating_point_precision(config: CoreasonBudgetConfig) -> None:
    """
    Verify precision with small numbers.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "float_user"

        # Add 0.0000001 10 times
        for _ in range(10):
            await mgr.record_spend(user_id, 0.0000001)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        val = await fake_redis.get(keys[0])

        # Redis INCRBYFLOAT uses double precision.
        # 10 * 1e-7 = 1e-6
        assert float(val) == pytest.approx(0.000001)

        await mgr.close()


@pytest.mark.asyncio
async def test_zero_cost(config: CoreasonBudgetConfig) -> None:
    """
    Verify recording 0 cost works and doesn't crash or expire keys weirdly.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "zero_user"

        await mgr.record_spend(user_id, 0.0)

        # Should create key with 0 usage
        keys = await fake_redis.keys(f"*user:{user_id}*")
        assert len(keys) == 1
        val = await fake_redis.get(keys[0])
        assert float(val) == 0.0

        await mgr.close()


@pytest.mark.asyncio
async def test_ttl_near_midnight(config: CoreasonBudgetConfig) -> None:
    """
    Mock time to be near midnight and verify TTL is calculated correctly.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # Mock datetime in guard
    # We need to patch datetime in the module where BudgetGuard is defined
    from datetime import datetime

    # 2023-10-27 23:59:00 UTC (60 seconds to midnight)
    mock_now = datetime(2023, 10, 27, 23, 59, 0)

    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
        patch("coreason_budget.guard.datetime") as mock_datetime,
    ):
        # Configure mock to return our time for .now(timezone.utc)
        # Note: timezone usage in code is datetime.now(timezone.utc)
        # We need to ensure the mock respects that
        mock_datetime.now.return_value = mock_now

        mgr = BudgetManager(config)
        user_id = "midnight_user"

        await mgr.record_spend(user_id, 10.0)

        keys = await fake_redis.keys(f"*user:{user_id}*")
        ttl = await fake_redis.ttl(keys[0])

        # Should be roughly 60 seconds
        assert 58 <= ttl <= 62

        await mgr.close()
