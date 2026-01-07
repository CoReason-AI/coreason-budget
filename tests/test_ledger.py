import pytest
from unittest.mock import MagicMock, patch
import fakeredis.aioredis
import fakeredis
from redis.exceptions import ConnectionError as RedisPyConnectionError
from redis.exceptions import RedisError
from coreason_budget.ledger import RedisLedger, SyncRedisLedger, LUA_INCREMENT_SCRIPT
from coreason_budget.exceptions import RedisConnectionError

# We need to test both Async and Sync ledgers

@pytest.mark.asyncio
async def test_async_ledger_increment_and_expiry() -> None:
    # Setup fakeredis
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    # We mock the from_url to return our fake_redis
    with patch("coreason_budget.ledger.from_url", return_value=fake_redis):
        ledger = RedisLedger("redis://localhost")

        # Explicitly call connect to cover that path
        await ledger.connect()

        # Test 1: Increment new key with TTL
        key = "test:budget:1"
        amount = 10.5
        ttl = 3600 # 1 hour

        new_val = await ledger.increment(key, amount, ttl)
        assert new_val == 10.5

        # Check Value
        val = await fake_redis.get(key)
        assert float(val) == 10.5

        # Check TTL
        # Note: fakeredis TTL might be slightly off or exact, usually exact for set
        actual_ttl = await fake_redis.ttl(key)
        assert 0 < actual_ttl <= 3600

        # Test 2: Increment existing key (TTL should NOT be reset if we pass new TTL,
        # based on the Lua script logic "if ttl == -1 then ...")
        # Wait, the Lua script logic says:
        # "if ttl == -1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end"
        # Since key has TTL now, it is NOT -1. So EXPIRE should NOT be called.

        # Let's verify this behavior.
        # Set a smaller TTL manually to check if it gets overwritten
        await fake_redis.expire(key, 100)

        await ledger.increment(key, 5.0, 3600)

        current_val = await fake_redis.get(key)
        assert float(current_val) == 15.5

        current_ttl = await fake_redis.ttl(key)
        # Should be around 100, not 3600
        assert current_ttl <= 100

        # Test get_usage
        usage = await ledger.get_usage(key)
        assert usage == 15.5

        # Test get_usage non-existent
        usage = await ledger.get_usage("missing")
        assert usage == 0.0

        await ledger.close()

def test_sync_ledger_increment_and_expiry() -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)

    with patch("coreason_budget.ledger.sync_from_url", return_value=fake_redis):
        ledger = SyncRedisLedger("redis://localhost")

        # Explicitly call connect
        ledger.connect()

        key = "test:budget:sync:1"
        amount = 20.0
        ttl = 60

        new_val = ledger.increment(key, amount, ttl)
        assert new_val == 20.0

        assert float(fake_redis.get(key)) == 20.0
        assert 0 < fake_redis.ttl(key) <= 60

        # Increment again
        new_val = ledger.increment(key, 10.0, 60)
        assert new_val == 30.0

        # Test get_usage
        usage = ledger.get_usage(key)
        assert usage == 30.0

        ledger.close()

@pytest.mark.asyncio
async def test_ledger_connection_error() -> None:
    # Simulate connection error
    with patch("coreason_budget.ledger.from_url") as mock_from_url:
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = RedisPyConnectionError("Connection refused")
        mock_from_url.return_value = mock_redis

        ledger = RedisLedger("redis://bad-url")

        with pytest.raises(RedisConnectionError, match="Could not connect to Redis"):
            await ledger.connect()

@pytest.mark.asyncio
async def test_ledger_get_error() -> None:
    with patch("coreason_budget.ledger.from_url") as mock_from_url:
        mock_redis = MagicMock()
        mock_redis.get.side_effect = RedisError("Read failed")
        mock_from_url.return_value = mock_redis

        ledger = RedisLedger("redis://localhost")

        with pytest.raises(RedisError):
            await ledger.get_usage("some-key")

@pytest.mark.asyncio
async def test_ledger_increment_error() -> None:
    with patch("coreason_budget.ledger.from_url") as mock_from_url:
        mock_redis = MagicMock()
        mock_redis.eval.side_effect = RedisError("Eval failed")
        mock_from_url.return_value = mock_redis

        ledger = RedisLedger("redis://localhost")

        with pytest.raises(RedisError):
            await ledger.increment("some-key", 10.0)

def test_sync_ledger_errors() -> None:
    with patch("coreason_budget.ledger.sync_from_url") as mock_from_url:
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis

        ledger = SyncRedisLedger("redis://localhost")

        # Connect Error
        mock_redis.ping.side_effect = RedisPyConnectionError("Connection refused")
        with pytest.raises(RedisConnectionError):
            ledger.connect()

        # Get Error
        mock_redis.get.side_effect = RedisError("Read failed")
        with pytest.raises(RedisError):
            ledger.get_usage("some-key")

        # Increment Error
        mock_redis.eval.side_effect = RedisError("Eval failed")
        with pytest.raises(RedisError):
            ledger.increment("some-key", 10.0)
