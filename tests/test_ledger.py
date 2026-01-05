# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fakeredis import aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from coreason_budget.ledger import RedisLedger


@pytest.fixture
def redis_url() -> str:
    return "redis://localhost:6379"


@pytest_asyncio.fixture
async def ledger(redis_url: str) -> RedisLedger:
    ledger = RedisLedger(redis_url)
    # Patch from_url to use fakeredis
    ledger._redis = aioredis.FakeRedis(decode_responses=True)
    return ledger


@pytest.mark.asyncio
async def test_ledger_connection_success(redis_url: str) -> None:
    """Test connection establishment success."""
    # We need to mock from_url to return a mock or fakeredis that doesn't fail ping
    mock_redis = MagicMock()
    # Ping must be awaitable
    mock_redis.ping = AsyncMock(return_value=True)

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        ledger = RedisLedger(redis_url)
        await ledger.connect()
        mock_redis.ping.assert_called_once()


@pytest.mark.asyncio
async def test_ledger_connection_failure(redis_url: str) -> None:
    """Test connection establishment failure."""
    # Since from_url is called in __init__, if it fails there, we catch it there.
    # But this test checks 'connect' method failure.
    # connect calls ping.
    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock(side_effect=RedisError("Connection refused"))

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        ledger = RedisLedger(redis_url)
        with pytest.raises(RedisConnectionError):
            await ledger.connect()


@pytest.mark.asyncio
async def test_close(ledger: RedisLedger) -> None:
    """Test close connection."""
    # _redis is a Mock in the fixture if patched, or FakeRedis.
    # FakeRedis.aclose is async.
    await ledger.close()
    # We don't set it to None anymore, we just close the pool.
    # So we check if aclose was called (if it's a mock) or just ensure no error.
    if isinstance(ledger._redis, MagicMock):
        ledger._redis.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_get_usage_with_mock(redis_url: str) -> None:
    """Test get_usage with mock."""
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        ledger = RedisLedger(redis_url)
        val = await ledger.get_usage("some_key")
        assert val == 0.0


@pytest.mark.asyncio
async def test_increment_with_mock(redis_url: str) -> None:
    """Test increment with mock."""
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=1.0)

    with patch("coreason_budget.ledger.from_url", return_value=mock_redis):
        ledger = RedisLedger(redis_url)
        await ledger.increment("some_key", 1.0)
        mock_redis.eval.assert_called_once()


@pytest.mark.asyncio
async def test_get_usage_error(ledger: RedisLedger) -> None:
    """Test error handling in get_usage."""
    # Force _redis.get to raise RedisError
    # We can mock the get method on the existing _redis instance
    # But _redis is a FakeRedis object.
    # Let's replace _redis with a MagicMock that raises.
    mock_redis = MagicMock()

    async def async_raise(*args: Any, **kwargs: Any) -> None:
        raise RedisError("Get failed")

    mock_redis.get.side_effect = async_raise
    ledger._redis = mock_redis

    with pytest.raises(RedisError):
        await ledger.get_usage("key")


@pytest.mark.asyncio
async def test_increment_error(ledger: RedisLedger) -> None:
    """Test error handling in increment."""
    mock_redis = MagicMock()

    async def async_raise(*args: Any, **kwargs: Any) -> None:
        raise RedisError("Eval failed")

    mock_redis.eval.side_effect = async_raise
    ledger._redis = mock_redis

    with pytest.raises(RedisError):
        await ledger.increment("key", 1.0)


@pytest.mark.asyncio
async def test_get_usage(ledger: RedisLedger) -> None:
    """Test getting usage for a key."""
    key = "test:usage"
    val = await ledger.get_usage(key)
    assert val == 0.0

    # We can assume _redis is not None because fixture sets it
    assert ledger._redis is not None
    await ledger._redis.set(key, "10.5")
    val = await ledger.get_usage(key)
    assert val == 10.5


@pytest.mark.asyncio
async def test_increment_no_ttl(ledger: RedisLedger) -> None:
    """Test increment without TTL."""
    key = "test:inc"
    new_val = await ledger.increment(key, 5.0)
    assert new_val == 5.0

    new_val = await ledger.increment(key, 2.5)
    assert new_val == 7.5

    # Check TTL is -1 (persist)
    assert ledger._redis is not None
    ttl = await ledger._redis.ttl(key)
    assert ttl == -1


@pytest.mark.asyncio
async def test_increment_with_ttl(ledger: RedisLedger) -> None:
    """Test increment with TTL."""
    key = "test:inc_ttl"
    ttl_seconds = 60

    # First increment sets TTL
    new_val = await ledger.increment(key, 10.0, ttl=ttl_seconds)
    assert new_val == 10.0

    assert ledger._redis is not None
    pttl = await ledger._redis.ttl(key)
    assert 0 < pttl <= ttl_seconds

    # Second increment should NOT reset TTL (if logic holds)
    await ledger._redis.expire(key, 10)
    await ledger.increment(key, 5.0, ttl=60)
    pttl = await ledger._redis.ttl(key)
    assert 0 < pttl <= 10


@pytest.mark.asyncio
async def test_increment_new_key_ttl(ledger: RedisLedger) -> None:
    """Verify separate keys get separate TTLs."""
    key1 = "k1"
    key2 = "k2"

    await ledger.increment(key1, 1, ttl=100)
    await ledger.increment(key2, 1, ttl=200)

    assert ledger._redis is not None
    t1 = await ledger._redis.ttl(key1)
    t2 = await ledger._redis.ttl(key2)

    assert 0 < t1 <= 100
    assert 100 < t2 <= 200
