# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from unittest.mock import AsyncMock, MagicMock

import pytest

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.guard import BudgetExceededError, BudgetGuard
from coreason_budget.ledger import RedisLedger


@pytest.fixture
def config() -> CoreasonBudgetConfig:
    return CoreasonBudgetConfig(daily_user_limit_usd=10.0, daily_project_limit_usd=100.0, daily_global_limit_usd=1000.0)


@pytest.fixture
def mock_ledger() -> MagicMock:
    ledger = MagicMock(spec=RedisLedger)
    ledger.get_usage = AsyncMock(return_value=0.0)
    ledger.increment = AsyncMock(return_value=1.0)
    return ledger


@pytest.fixture
def guard(config: CoreasonBudgetConfig, mock_ledger: MagicMock) -> BudgetGuard:
    return BudgetGuard(config, mock_ledger)


@pytest.mark.asyncio
async def test_check_availability_pass(guard: BudgetGuard, mock_ledger: MagicMock) -> None:
    """Test check passes when under limit."""
    mock_ledger.get_usage.return_value = 5.0
    await guard.check_availability("user1", "proj1")
    # Should check Global, Project, User (3 checks)
    assert mock_ledger.get_usage.call_count == 3


@pytest.mark.asyncio
async def test_check_availability_user_limit(guard: BudgetGuard, mock_ledger: MagicMock) -> None:
    """Test user limit exceeded."""
    # Setup: Global=0, Project=0, User=10.0 (Limit 10.0)
    # The order of checks in code is Global, Project, User.
    # We need side_effect to return different values for different keys.

    async def get_usage_side_effect(key: str) -> float:
        if "user" in key:
            return 10.0
        return 0.0

    mock_ledger.get_usage.side_effect = get_usage_side_effect

    with pytest.raises(BudgetExceededError, match="User user1 daily limit"):
        await guard.check_availability("user1", "proj1")


@pytest.mark.asyncio
async def test_check_availability_global_limit(guard: BudgetGuard, mock_ledger: MagicMock) -> None:
    """Test global limit exceeded."""

    async def get_usage_side_effect(key: str) -> float:
        if "global" in key:
            return 1000.0
        return 0.0

    mock_ledger.get_usage.side_effect = get_usage_side_effect

    with pytest.raises(BudgetExceededError, match="Global daily limit"):
        await guard.check_availability("user1")


@pytest.mark.asyncio
async def test_record_spend(guard: BudgetGuard, mock_ledger: MagicMock) -> None:
    """Test recording spend."""
    await guard.record_spend("user1", 0.5, "proj1")

    # Should increment 3 times (Global, Project, User)
    assert mock_ledger.increment.call_count == 3
    # Verify arguments
    calls = mock_ledger.increment.call_args_list
    assert len(calls) == 3
    # Check that TTL was passed (should be an int > 0)
    _, kwargs = calls[0]
    assert "ttl" in kwargs
    assert isinstance(kwargs["ttl"], int)
    assert kwargs["ttl"] > 0


def test_get_keys_and_limits(guard: BudgetGuard) -> None:
    """Test key generation logic."""
    # Mock date for stable keys? Or just check format.
    # We can mock _get_date_str
    guard._get_date_str = lambda: "2023-01-01"  # type: ignore[method-assign]

    items = guard._get_keys_and_limits("u1", "p1")
    assert len(items) == 3

    global_key, g_lim, _ = items[0]
    assert global_key == "spend:v1:global:2023-01-01"
    assert g_lim == 1000.0

    proj_key, p_lim, _ = items[1]
    assert proj_key == "spend:v1:project:p1:2023-01-01"
    assert p_lim == 100.0

    user_key, u_lim, _ = items[2]
    assert user_key == "spend:v1:user:u1:2023-01-01"
    assert u_lim == 10.0


def test_ttl_calculation(guard: BudgetGuard) -> None:
    """Test TTL calculation sanity."""
    ttl = guard._get_ttl_seconds()
    assert 0 < ttl <= 86400
