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
from unittest.mock import MagicMock, patch

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
    ledger = RedisLedger(redis_url)
    # We need to mock from_url to return a mock or fakeredis that doesn't fail ping
    with patch("coreason_budget.ledger.from_url") as mock_from_url:
        mock_redis = MagicMock()

        # Ping must be awaitable
        async def async_ping() -> bool:
            return True

        mock_redis.ping.side_effect = async_ping
        mock_from_url.return_value = mock_redis

        await ledger.connect()
        mock_from_url.assert_called_once()
        # Verify logging? Implicitly covered if no error.


@pytest.mark.asyncio
async def test_ledger_connection_failure(redis_url: str) -> None:
    """Test connection establishment failure."""
    ledger = RedisLedger(redis_url)
    with patch("coreason_budget.ledger.from_url") as mock_from_url:
        mock_from_url.side_effect = RedisError("Connection refused")
        with pytest.raises(RedisConnectionError):
            await ledger.connect()


@pytest.mark.asyncio
async def test_close(ledger: RedisLedger) -> None:
    """Test close connection."""
    await ledger.close()
    assert ledger._redis is None


@pytest.mark.asyncio
async def test_auto_connect_get_usage(redis_url: str) -> None:
    """Test auto-connect in get_usage."""
    ledger = RedisLedger(redis_url)
    # Mock connect to populate _redis
    with patch.object(RedisLedger, "connect") as mock_connect:
        # We need _redis to be set after connect, or we manually set it
        # But connect is mocked, so we must simulate what it does or set _redis beforehand?
        # No, the code calls connect(), then asserts _redis is not None.
        # So our mock_connect should set _redis.
        async def side_effect() -> None:
            ledger._redis = aioredis.FakeRedis(decode_responses=True)

        mock_connect.side_effect = side_effect

        val = await ledger.get_usage("some_key")
        assert val == 0.0
        mock_connect.assert_called_once()


@pytest.mark.asyncio
async def test_auto_connect_increment(redis_url: str) -> None:
    """Test auto-connect in increment."""
    ledger = RedisLedger(redis_url)
    with patch.object(RedisLedger, "connect") as mock_connect:

        async def side_effect() -> None:
            ledger._redis = aioredis.FakeRedis(decode_responses=True)

        mock_connect.side_effect = side_effect

        await ledger.increment("some_key", 1.0)
        mock_connect.assert_called_once()


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
