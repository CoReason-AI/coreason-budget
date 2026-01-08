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

import pytest_asyncio
from fakeredis import aioredis

from coreason_budget import BudgetConfig, BudgetManager


@pytest_asyncio.fixture
async def manager() -> AsyncGenerator[BudgetManager, None]:
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=10.0)
    mgr = BudgetManager(config)

    # Let's manually inject a fake redis client into the ledger
    # Updated: BudgetManager no longer exposes .ledger directly, it has ._async_ledger
    # And ._async_ledger._redis
    mgr._async_ledger._redis = aioredis.FakeRedis(decode_responses=True)

    yield mgr
    await mgr.close()
