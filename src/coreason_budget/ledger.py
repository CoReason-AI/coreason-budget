# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from typing import Optional

from redis import Redis as SyncRedis
from redis import from_url as sync_from_url
from redis.asyncio import Redis, from_url
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from coreason_budget.utils.logger import logger

LUA_INCREMENT_SCRIPT = """
local current = redis.call("INCRBYFLOAT", KEYS[1], ARGV[1])
if ARGV[2] ~= "nil" then
    local ttl = redis.call("TTL", KEYS[1])
    -- If key has no expiry (ttl == -1) or is new, set it.
    -- Actually, if we pass a TTL, we usually mean "ensure this key expires in X seconds".
    -- But for a daily budget, if we set it to 24h at 10AM, and then update at 11AM,
    -- we don't want to reset it to 24h. We want to keep the original expiry.
    -- Ideally the caller provides the remaining seconds to midnight.
    -- If the key already exists, its TTL is ticking.
    -- So we only set EXPIRE if TTL is -1 (no expiry) or if the key was just created.
    if ttl == -1 then
        redis.call("EXPIRE", KEYS[1], ARGV[2])
    end
end
return current
"""


class RedisLedger:
    """Manages Redis connections and atomic operations for budget tracking."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        # redis-py handles connection pooling automatically.
        # We initialize it here but it connects lazily.
        self._redis: Redis = from_url(self.redis_url, encoding="utf-8", decode_responses=True)

    async def connect(self) -> None:
        """
        Verify connection to Redis.
        Strictly required for 'Fail Closed' startup checks.
        """
        try:
            await self._redis.ping()
            logger.info("Connected to Redis at {}", self.redis_url)
        except RedisError as e:
            logger.error("Failed to connect to Redis: {}", e)
            raise RedisConnectionError(f"Could not connect to Redis: {e}") from e

    async def close(self) -> None:
        """Close the Redis connection pool."""
        await self._redis.aclose()
        logger.info("Closed Redis connection")

    async def get_usage(self, key: str) -> float:
        """Get current usage for a key. Returns 0.0 if key does not exist."""
        try:
            val = await self._redis.get(key)
            return float(val) if val else 0.0
        except RedisError as e:
            logger.error("Redis GET error for key {}: {}", key, e)
            raise

    async def increment(self, key: str, amount: float, ttl: Optional[int] = None) -> float:
        """
        Atomically increment a key by amount.
        If ttl is provided and key is new (or has no expiry?), set expiry.

        For daily limits, we typically want to set expiry on first creation.
        If the key exists, we just increment.

        Returns the new value.
        """
        try:
            # Redis Lua arguments are strings
            ttl_arg = str(ttl) if ttl is not None else "nil"
            result = await self._redis.eval(LUA_INCREMENT_SCRIPT, 1, key, str(amount), ttl_arg)
            return float(result)
        except RedisError as e:
            logger.error("Redis INCRBYFLOAT error for key {}: {}", key, e)
            raise


class SyncRedisLedger:
    """Manages Synchronous Redis connections and atomic operations for budget tracking."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: SyncRedis = sync_from_url(self.redis_url, encoding="utf-8", decode_responses=True)

    def connect(self) -> None:
        """
        Verify connection to Redis.
        Strictly required for 'Fail Closed' startup checks.
        """
        try:
            self._redis.ping()
            logger.info("Connected to Redis at {}", self.redis_url)
        except RedisError as e:
            logger.error("Failed to connect to Redis: {}", e)
            raise RedisConnectionError(f"Could not connect to Redis: {e}") from e

    def close(self) -> None:
        """Close the Redis connection pool."""
        self._redis.close()
        logger.info("Closed Redis connection")

    def get_usage(self, key: str) -> float:
        """Get current usage for a key. Returns 0.0 if key does not exist."""
        try:
            val = self._redis.get(key)
            return float(val) if val else 0.0
        except RedisError as e:
            logger.error("Redis GET error for key {}: {}", key, e)
            raise

    def increment(self, key: str, amount: float, ttl: Optional[int] = None) -> float:
        """
        Atomically increment a key by amount.
        Returns the new value.
        """
        try:
            ttl_arg = str(ttl) if ttl is not None else "nil"
            result = self._redis.eval(LUA_INCREMENT_SCRIPT, 1, key, str(amount), ttl_arg)
            return float(result)
        except RedisError as e:
            logger.error("Redis INCRBYFLOAT error for key {}: {}", key, e)
            raise
