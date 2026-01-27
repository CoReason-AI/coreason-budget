from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from coreason_identity.models import UserContext

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.manager import BudgetManager


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(redis_url="redis://localhost")


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(user_id="user1", email="user1@example.com", groups=[], scopes=[], claims={})


@pytest.mark.asyncio
async def test_manager_async_flow(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    # Mock at the Redis level
    with patch("coreason_budget.ledger.from_url") as mock_async_redis, patch("coreason_budget.ledger.sync_from_url"):
        # Setup mocks
        mock_async = AsyncMock()
        mock_async_redis.return_value = mock_async
        # get returning 0.0
        mock_async.get.return_value = "0.0"

        mgr = BudgetManager(config)

        # Check
        available = await mgr.check_availability(user_context, "proj1", 0.5)
        assert available is True

        # Charge
        mock_async.eval.return_value = "1.0"
        await mgr.record_spend(user_context, 0.5, "proj1")

        # Verify calls
        assert mock_async.get.call_count >= 1
        assert mock_async.eval.call_count >= 1

        await mgr.close()


def test_manager_sync_flow(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    with patch("coreason_budget.ledger.from_url"), patch("coreason_budget.ledger.sync_from_url") as mock_sync_redis:
        mock_sync = MagicMock()
        mock_sync_redis.return_value = mock_sync
        mock_sync.get.return_value = "0.0"
        mock_sync.eval.return_value = "1.0"

        mgr = BudgetManager(config)

        available = mgr.check_availability_sync(user_context, "proj1", 0.5)
        assert available is True

        mgr.record_spend_sync(user_context, 0.5, "proj1")

        assert mock_sync.get.call_count >= 1
        assert mock_sync.eval.call_count >= 1

        # close calls sync_ledger.close
        mgr._sync_ledger.close()


def test_manager_pricing_access(config: CoreasonBudgetConfig) -> None:
    with patch("coreason_budget.ledger.from_url"), patch("coreason_budget.ledger.sync_from_url"):
        mgr = BudgetManager(config)
        assert mgr.pricing is not None
        # Just ensure we can call it (mocks internal)
        with patch("coreason_budget.pricing.litellm.completion_cost", return_value=0.1):
            cost = mgr.pricing.calculate("gpt-4", 100, 100)
            assert cost == 0.1
