import redis.asyncio as redis
import time
from datetime import datetime, timezone, timedelta

class RedisLedger:
    """
    Component B: RedisLedger (The Bank)
    Manages Redis connections and atomic operations.
    """

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    async def close(self):
        await self.redis.close()

    def _get_midnight_timestamp(self) -> int:
        """Get the Unix timestamp for the next UTC midnight."""
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp())

    async def increment(self, key: str, amount: float) -> float:
        """
        Atomically increment the spend for a key and set expiry if needed.
        """
        # Lua script to increment and set expiry if not set (or if no expiry exists)
        # We set expiry to next midnight.
        # ARGV[1] is amount, ARGV[2] is expiry timestamp
        script = """
        local current = redis.call("INCRBYFLOAT", KEYS[1], ARGV[1])
        if redis.call("TTL", KEYS[1]) == -1 then
            redis.call("EXPIREAT", KEYS[1], ARGV[2])
        end
        return current
        """
        expiry_timestamp = self._get_midnight_timestamp()

        # redis-py handles converting float to string for Redis
        return float(await self.redis.eval(script, 1, key, amount, expiry_timestamp))

    async def get_current_usage(self, key: str) -> float:
        """Get current usage for a key."""
        value = await self.redis.get(key)
        return float(value) if value else 0.0
