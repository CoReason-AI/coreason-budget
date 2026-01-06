# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from coreason_budget import BudgetManager


@pytest.mark.asyncio
async def test_fail_closed_on_redis_outage(manager: BudgetManager) -> None:
    """
    Verify 'Fail Closed' behavior:
    If Redis is down during check_availability, it must raise an exception
    (stopping the LLM call), rather than returning None/True (Fail Open).
    """
    # Mock ledger.get_usage to raise ConnectionError
    with patch.object(manager.ledger, "get_usage", side_effect=RedisConnectionError("Connection refused")):
        # Should raise RedisConnectionError (or subclass of RedisError)
        with pytest.raises(RedisConnectionError):
            await manager.check_availability("user_fail_closed")


@pytest.mark.asyncio
async def test_pricing_failure_propagation(manager: BudgetManager) -> None:
    """
    Verify that if pricing calculation fails, we don't record $0.0 blindly.
    The integration pattern requires the caller to calculate cost.
    We test that the PricingEngine raises exception on failure.
    """
    # Mock litellm.completion_cost to raise Exception
    with patch("litellm.completion_cost", side_effect=ValueError("Model not found")):
        with pytest.raises(ValueError, match="Model not found"):
            manager.pricing.calculate("unknown-model", 10, 10)


@pytest.mark.asyncio
async def test_partial_check_failure(manager: BudgetManager) -> None:
    """
    Verify behavior when Redis fails mid-check.
    e.g., Global check succeeds, Project check fails.
    Must raise exception (Fail Closed).
    """

    # We mock get_usage to succeed once then fail
    async def side_effect(key: str) -> float:
        if "global" in key:
            return 0.0
        raise RedisConnectionError("Redis died")

    with patch.object(manager.ledger, "get_usage", side_effect=side_effect):
        with pytest.raises(RedisConnectionError):
            await manager.check_availability("user_mid_fail", project_id="proj_mid_fail")
