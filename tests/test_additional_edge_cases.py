from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError, RedisConnectionError
from coreason_budget.manager import BudgetManager


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(
        redis_url="redis://localhost",
        daily_global_limit_usd=1000.0,
        daily_project_limit_usd=500.0,
        daily_user_limit_usd=100.0,
    )


@pytest.mark.asyncio
async def test_hierarchy_strictness(config: CoreasonBudgetConfig) -> None:
    """
    Verify that the strictest limit (lowest remaining budget) triggers the failure.
    Or rather, that if *any* limit is crossed, it fails.
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "hierarchy_user"
        project_id = "hierarchy_project"

        # Scenario 1: User limit exceeded
        # Set user usage to 101 (Limit 100)
        await fake_redis.set(f"budget:user:{user_id}:{mgr.guard._get_date_str()}", 101.0)
        with pytest.raises(BudgetExceededError, match="User daily limit exceeded"):
            await mgr.check_availability(user_id, project_id, 1.0)

        # Cleanup
        await fake_redis.flushall()

        # Scenario 2: Project limit exceeded
        # User usage 10 (OK), Project usage 501 (Limit 500)
        await fake_redis.set(f"budget:user:{user_id}:{mgr.guard._get_date_str()}", 10.0)
        await fake_redis.set(f"budget:project:{project_id}:{mgr.guard._get_date_str()}", 501.0)
        with pytest.raises(BudgetExceededError, match="Project daily limit exceeded"):
            await mgr.check_availability(user_id, project_id, 1.0)

        # Cleanup
        await fake_redis.flushall()

        # Scenario 3: Global limit exceeded
        # User 10, Project 100, Global 1001 (Limit 1000)
        await fake_redis.set(f"budget:user:{user_id}:{mgr.guard._get_date_str()}", 10.0)
        await fake_redis.set(f"budget:project:{project_id}:{mgr.guard._get_date_str()}", 100.0)
        await fake_redis.set(f"budget:global:{mgr.guard._get_date_str()}", 1001.0)
        with pytest.raises(BudgetExceededError, match="Global daily limit exceeded"):
            await mgr.check_availability(user_id, project_id, 1.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_corrupted_data_handling(config: CoreasonBudgetConfig) -> None:
    """
    If Redis returns non-numeric data, it should raise a ValueError (fail closed/error).
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "corrupt_user"

        # Set corrupted data
        key = f"budget:user:{user_id}:{mgr.guard._get_date_str()}"
        await fake_redis.set(key, "not-a-number")

        with pytest.raises(ValueError):
            await mgr.check_availability(user_id, estimated_cost=1.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_sync_async_interoperability(config: CoreasonBudgetConfig) -> None:
    """
    Verify that sync and async managers sharing the same backend see the same data.
    """
    # Create a shared fake redis backend (thread-safe enough for this test)
    # fakeredis.aioredis and fakeredis.FakeRedis can share the same server if configured?
    # Actually, we can just point them to the same dict or server instance.
    # Easier way: Mock the underlying redis client in both ledgers to point to compatible fakes
    # or the SAME fake instance if possible.

    # fakeredis supports sharing state via `server` argument.
    server = fakeredis.FakeServer()
    async_fake = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    sync_fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    with (
        patch("coreason_budget.ledger.from_url", return_value=async_fake),
        patch("coreason_budget.ledger.sync_from_url", return_value=sync_fake),
    ):
        mgr = BudgetManager(config)
        user_id = "interop_user"

        # 1. Record spend via Sync
        mgr.record_spend_sync(user_id, 10.0)

        # 2. Check usage via Async
        # We can't ask check_availability for the number, but we can try to spend more.
        # Limit is 100. Used 10. Spending 91 should fail.
        result = await mgr.check_availability(user_id, estimated_cost=80.0)
        assert result is True

        # Spend 91 -> Total 101 -> Fail
        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(user_id, estimated_cost=91.0)

        # 3. Record spend via Async
        await mgr.record_spend(user_id, 20.0)
        # Total now 30.

        # 4. Check usage via Sync
        # Sync check 71 -> Total 101 -> Fail
        with pytest.raises(BudgetExceededError):
            mgr.check_availability_sync(user_id, estimated_cost=71.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_fail_closed_connection_error(config: CoreasonBudgetConfig) -> None:
    """
    Verify that if Redis connection fails, the system fails closed (raises error),
    preventing the transaction.
    """
    # We mock the ledger instance directly to raise error
    with patch("coreason_budget.ledger.RedisLedger.get_usage", side_effect=RedisConnectionError("Fail")):
        mgr = BudgetManager(config)

        # Should raise RedisConnectionError, effectively blocking execution
        with pytest.raises(RedisConnectionError):
            await mgr.check_availability("user1")

        # Note: We don't need to close mgr here because we mocked the ledger methods,
        # but safely calling close doesn't hurt.
        await mgr.close()
