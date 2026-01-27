from unittest.mock import patch

import fakeredis
import fakeredis.aioredis
import pytest
from coreason_identity.models import UserContext

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


def create_context(user_id: str) -> UserContext:
    return UserContext(user_id=user_id, email=f"{user_id}@example.com", groups=[], scopes=[], claims={})


@pytest.mark.asyncio
async def test_hierarchy_strictness(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "hierarchy_user"
        context = create_context(user_id)
        project_id = "hierarchy_project"

        # Scenario 1: User limit exceeded
        await fake_redis.set(f"budget:user:{user_id}:{mgr.guard._get_date_str()}", 101.0)
        with pytest.raises(BudgetExceededError, match="User daily limit exceeded"):
            await mgr.check_availability(context, project_id, 1.0)

        await fake_redis.flushall()

        # Scenario 2: Project limit exceeded
        await fake_redis.set(f"budget:user:{user_id}:{mgr.guard._get_date_str()}", 10.0)
        await fake_redis.set(f"budget:project:{project_id}:{mgr.guard._get_date_str()}", 501.0)
        with pytest.raises(BudgetExceededError, match="Project daily limit exceeded"):
            await mgr.check_availability(context, project_id, 1.0)

        await fake_redis.flushall()

        # Scenario 3: Global limit exceeded
        await fake_redis.set(f"budget:user:{user_id}:{mgr.guard._get_date_str()}", 10.0)
        await fake_redis.set(f"budget:project:{project_id}:{mgr.guard._get_date_str()}", 100.0)
        await fake_redis.set(f"budget:global:{mgr.guard._get_date_str()}", 1001.0)
        with pytest.raises(BudgetExceededError, match="Global daily limit exceeded"):
            await mgr.check_availability(context, project_id, 1.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_corrupted_data_handling(config: CoreasonBudgetConfig) -> None:
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("coreason_budget.ledger.from_url", return_value=fake_redis),
        patch("coreason_budget.ledger.sync_from_url"),
    ):
        mgr = BudgetManager(config)
        user_id = "corrupt_user"
        context = create_context(user_id)

        key = f"budget:user:{user_id}:{mgr.guard._get_date_str()}"
        await fake_redis.set(key, "not-a-number")

        with pytest.raises(ValueError):
            await mgr.check_availability(context, estimated_cost=1.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_sync_async_interoperability(config: CoreasonBudgetConfig) -> None:
    server = fakeredis.FakeServer()
    async_fake = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    sync_fake = fakeredis.FakeRedis(server=server, decode_responses=True)

    with (
        patch("coreason_budget.ledger.from_url", return_value=async_fake),
        patch("coreason_budget.ledger.sync_from_url", return_value=sync_fake),
    ):
        mgr = BudgetManager(config)
        user_id = "interop_user"
        context = create_context(user_id)

        mgr.record_spend_sync(context, 10.0)

        result = await mgr.check_availability(context, estimated_cost=80.0)
        assert result is True

        with pytest.raises(BudgetExceededError):
            await mgr.check_availability(context, estimated_cost=91.0)

        await mgr.record_spend(context, 20.0)

        with pytest.raises(BudgetExceededError):
            mgr.check_availability_sync(context, estimated_cost=71.0)

        await mgr.close()


@pytest.mark.asyncio
async def test_fail_closed_connection_error(config: CoreasonBudgetConfig) -> None:
    with patch("coreason_budget.ledger.RedisLedger.get_usage", side_effect=RedisConnectionError("Fail")):
        mgr = BudgetManager(config)
        context = create_context("user1")

        with pytest.raises(RedisConnectionError):
            await mgr.check_availability(context)

        await mgr.close()
