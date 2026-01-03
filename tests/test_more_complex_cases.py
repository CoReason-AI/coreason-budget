# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from coreason_budget import BudgetManager
from coreason_budget.ledger import RedisLedger


@pytest.mark.asyncio
async def test_lua_ttl_logic_new_key() -> None:
    """
    Test Lua script sets TTL if key is new.
    """
    from fakeredis.aioredis import FakeRedis

    fake_redis = FakeRedis(decode_responses=True)

    ledger = RedisLedger("redis://localhost:6379")
    ledger._redis = fake_redis

    key = "test_ttl_new"
    ttl = 3600

    # New key, should set TTL
    await ledger.increment(key, 10.0, ttl=ttl)

    actual_ttl = await fake_redis.ttl(key)
    # FakeRedis might return 3600 or slightly less.
    assert actual_ttl > 0 and actual_ttl <= 3600


@pytest.mark.asyncio
async def test_lua_ttl_logic_existing_key_no_expiry() -> None:
    """
    Test Lua script sets TTL if key exists but has no expiry (ttl=-1).
    """
    from fakeredis.aioredis import FakeRedis

    fake_redis = FakeRedis(decode_responses=True)
    ledger = RedisLedger("redis://localhost:6379")
    ledger._redis = fake_redis

    key = "test_ttl_no_expiry"
    # Create key without expiry
    await fake_redis.set(key, 5.0)
    assert await fake_redis.ttl(key) == -1

    # Increment with TTL
    await ledger.increment(key, 10.0, ttl=3600)

    # Should now have TTL
    actual_ttl = await fake_redis.ttl(key)
    assert actual_ttl > 0


@pytest.mark.asyncio
async def test_lua_ttl_logic_existing_key_with_expiry() -> None:
    """
    Test Lua script does NOT update TTL if key already has one.
    """
    from fakeredis.aioredis import FakeRedis

    fake_redis = FakeRedis(decode_responses=True)
    ledger = RedisLedger("redis://localhost:6379")
    ledger._redis = fake_redis

    key = "test_ttl_preserve"
    # Create key with expiry of 100s
    await fake_redis.set(key, 5.0)
    await fake_redis.expire(key, 100)

    assert await fake_redis.ttl(key) > 0

    # Increment with different TTL (e.g. 3600)
    await ledger.increment(key, 10.0, ttl=3600)

    # Should preserve roughly 100s
    actual_ttl = await fake_redis.ttl(key)
    assert actual_ttl <= 100


@pytest.mark.asyncio
async def test_ledger_connect_exception_propagation() -> None:
    """Explicitly verify propagation of RedisConnectionError in connect."""
    ledger = RedisLedger("redis://localhost:6379")
    mock_redis = MagicMock()
    # Mock ping to raise RedisError
    mock_redis.ping = AsyncMock(side_effect=RedisError("Ping fail"))

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        with pytest.raises(RedisConnectionError, match="Could not connect to Redis"):
            await ledger.connect()


@pytest.mark.asyncio
async def test_ledger_close_log() -> None:
    """Explicitly verify log message in close."""
    ledger = RedisLedger("redis://localhost:6379")
    mock_redis = MagicMock()
    mock_redis.aclose = AsyncMock()
    ledger._redis = mock_redis

    with patch("coreason_budget.ledger.logger") as mock_logger:
        await ledger.close()
        mock_logger.info.assert_called_with("Closed Redis connection")


# Validation Edge Cases (Manager)
@pytest.mark.asyncio
async def test_manager_input_validation_empty_strings(manager: BudgetManager) -> None:
    """Test empty strings for project_id and model in record_spend."""
    # Coverage lines 62, 64, 66 in manager.py

    # Valid user_id
    user_id = "u"

    # Empty project_id
    with pytest.raises(ValueError, match="project_id must be a non-empty string"):
        await manager.record_spend(user_id, 1.0, project_id="", model="m")

    # Whitespace project_id
    with pytest.raises(ValueError, match="project_id must be a non-empty string"):
        await manager.record_spend(user_id, 1.0, project_id="   ", model="m")

    # Empty model
    with pytest.raises(ValueError, match="model must be a non-empty string"):
        await manager.record_spend(user_id, 1.0, project_id="p", model="")

    # Whitespace model
    with pytest.raises(ValueError, match="model must be a non-empty string"):
        await manager.record_spend(user_id, 1.0, project_id="p", model="  ")


# Pricing Error
@pytest.mark.asyncio
async def test_pricing_re_raise_error(manager: BudgetManager) -> None:
    """Test that pricing engine re-raises exceptions."""
    # Coverage line 47 in pricing.py
    with patch("coreason_budget.pricing.litellm.completion_cost", side_effect=ValueError("Bad math")):
        with pytest.raises(ValueError, match="Bad math"):
            manager.pricing.calculate("m", 1, 1)


# Logger Init
def test_logger_mkdir() -> None:
    """Test that logger creates directory if missing."""
    # This is tricky as we need to reload the module or run in subprocess.
    # Subprocess is cleaner.
    import subprocess
    import sys

    cmd = """
import sys
import shutil
from pathlib import Path

# Delete logs dir if exists
p = Path("logs")
if p.exists():
    shutil.rmtree(p)

assert not p.exists()

# Import logger should trigger creation
from coreason_budget.utils import logger
assert p.exists()
"""
    result = subprocess.run([sys.executable, "-c", cmd], capture_output=True)
    assert result.returncode == 0, f"Subprocess failed: {result.stderr.decode()}"
