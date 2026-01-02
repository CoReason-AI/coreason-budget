# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from coreason_budget import BudgetConfig, BudgetExceededError, BudgetManager
from fakeredis import aioredis


@pytest_asyncio.fixture
async def manager() -> AsyncGenerator[BudgetManager, None]:
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=10.0)
    mgr = BudgetManager(config)

    # Mock connection in ledger to use fakeredis
    # Since BudgetManager initializes RedisLedger internally, we need to patch it
    # OR we can access mgr.ledger and patch its internal _redis if we connect first?
    # Better: Patch RedisLedger.connect or patch from_url during the test.

    # Let's manually inject a fake redis client into the ledger
    mgr.ledger._redis = aioredis.FakeRedis(decode_responses=True)

    yield mgr
    await mgr.close()


@pytest.mark.asyncio
async def test_end_to_end_flow(manager: BudgetManager) -> None:
    """Test the complete check -> run -> charge flow."""
    user_id = "user_e2e"

    # 1. Pre-flight check (should pass)
    await manager.check_availability(user_id)

    # 2. Calculate cost
    # Mock pricing for predictability
    with patch("coreason_budget.pricing.litellm.completion_cost", return_value=0.05):
        cost = manager.pricing.calculate("gpt-4", 100, 100)
    assert cost == 0.05

    # 3. Record spend
    await manager.record_spend(user_id, cost)

    # Verify spend in Redis
    # We can access internal ledger to verify
    # Key construction: spend:v1:user:{user_id}:{date}
    # We can use the guard to get the key? No, internal method.
    # Just check that it's > 0
    # Actually, let's just do another check.

    # 4. Check availability again (should pass)
    await manager.check_availability(user_id)


@pytest.mark.asyncio
async def test_budget_exceeded_flow(manager: BudgetManager) -> None:
    """Test flow where budget is exceeded."""
    user_id = "user_broke"
    limit = manager.config.daily_user_limit_usd  # 10.0

    # Record enough spend to reach limit
    await manager.record_spend(user_id, limit)

    # Verify check fails
    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id)


@pytest.mark.asyncio
async def test_pricing_integration(manager: BudgetManager) -> None:
    """Test pricing engine access."""
    assert manager.pricing is not None
    # We mocked litellm in unit tests, here we might want to check it works or mock again.
    # Since we don't have API keys, real calls fail.
    # So we mock.
    with patch("coreason_budget.pricing.litellm.completion_cost", return_value=1.0):
        cost = manager.pricing.calculate("m", 1, 1)
        assert cost == 1.0
