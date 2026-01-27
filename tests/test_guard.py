from unittest.mock import AsyncMock, MagicMock

import pytest

from coreason_identity.models import UserContext
from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError
from coreason_budget.guard import BudgetGuard, SyncBudgetGuard
from coreason_budget.ledger import RedisLedger, SyncRedisLedger


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(
        redis_url="redis://localhost",
        daily_global_limit_usd=100.0,
        daily_project_limit_usd=50.0,
        daily_user_limit_usd=10.0,
    )

@pytest.fixture
def user_context() -> UserContext:
    return UserContext(
        user_id="user1",
        email="user1@example.com",
        groups=[],
        scopes=[],
        claims={}
    )


@pytest.mark.asyncio
async def test_guard_check_success(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=RedisLedger)
    ledger.get_usage = AsyncMock(return_value=0.0)

    guard = BudgetGuard(config, ledger)

    # Should pass
    result = await guard.check(user_context, "proj1", 5.0)
    assert result is True

    # Verify calls
    # Should check global, project, user
    assert ledger.get_usage.call_count == 3


@pytest.mark.asyncio
async def test_guard_check_global_limit(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=RedisLedger)
    # Global limit is 100. Return 99.
    # Estimated cost 2. Total 101 > 100.
    ledger.get_usage = AsyncMock(return_value=99.0)

    guard = BudgetGuard(config, ledger)

    with pytest.raises(BudgetExceededError, match="Global daily limit exceeded"):
        await guard.check(user_context, "proj1", 2.0)


@pytest.mark.asyncio
async def test_guard_check_project_limit(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=RedisLedger)
    # Global OK (0), Project limit 50. Return 49.
    # User OK (0).
    # Need to mock sequence of returns: global, project, user
    # Order in code: Global, Project, User
    ledger.get_usage = AsyncMock(side_effect=[0.0, 49.0, 0.0])

    guard = BudgetGuard(config, ledger)

    with pytest.raises(BudgetExceededError, match="Project daily limit exceeded"):
        await guard.check(user_context, "proj1", 2.0)


@pytest.mark.asyncio
async def test_guard_check_user_limit(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=RedisLedger)
    # Global OK, Project OK, User limit 10. Return 9.
    ledger.get_usage = AsyncMock(side_effect=[0.0, 0.0, 9.0])

    guard = BudgetGuard(config, ledger)

    with pytest.raises(BudgetExceededError, match="User daily limit exceeded"):
        await guard.check(user_context, "proj1", 2.0)


@pytest.mark.asyncio
async def test_guard_charge(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=RedisLedger)
    ledger.increment = AsyncMock()

    guard = BudgetGuard(config, ledger)

    await guard.charge(user_context, 5.0, "proj1")

    assert ledger.increment.call_count == 3  # Global, Project, User
    # Verify owner_id was passed
    # Check last call args
    call_args = ledger.increment.call_args
    # call_args is (args, kwargs)
    # increment(key, amount, owner_id=..., ttl=...)
    assert call_args.kwargs['owner_id'] == "user1"


def test_sync_guard_check_success(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=SyncRedisLedger)
    ledger.get_usage.return_value = 0.0

    guard = SyncBudgetGuard(config, ledger)

    assert guard.check(user_context, "proj1", 5.0) is True


def test_sync_guard_check_user_limits(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=SyncRedisLedger)
    guard = SyncBudgetGuard(config, ledger)

    # User limit
    ledger.get_usage.side_effect = [0.0, 0.0, 9.0]
    with pytest.raises(BudgetExceededError, match="User daily limit exceeded"):
        guard.check(user_context, "proj1", 2.0)


def test_sync_guard_check_global_limit(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=SyncRedisLedger)
    guard = SyncBudgetGuard(config, ledger)

    # Global limit exceeded
    ledger.get_usage.side_effect = [99.0]
    with pytest.raises(BudgetExceededError, match="Global daily limit exceeded"):
        guard.check(user_context, "proj1", 2.0)


def test_sync_guard_check_project_limit(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=SyncRedisLedger)
    guard = SyncBudgetGuard(config, ledger)

    # Project limit exceeded
    ledger.get_usage.side_effect = [0.0, 49.0]
    with pytest.raises(BudgetExceededError, match="Project daily limit exceeded"):
        guard.check(user_context, "proj1", 2.0)


def test_sync_guard_charge(config: CoreasonBudgetConfig, user_context: UserContext) -> None:
    ledger = MagicMock(spec=SyncRedisLedger)
    guard = SyncBudgetGuard(config, ledger)

    guard.charge(user_context, 5.0, "proj1")

    assert ledger.increment.call_count == 3
    assert ledger.increment.call_args.kwargs['owner_id'] == "user1"
