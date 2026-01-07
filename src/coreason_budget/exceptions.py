class BudgetExceededError(Exception):
    """Raised when a budget limit is exceeded."""

    pass


class RedisConnectionError(Exception):
    """Raised when the Redis connection fails."""

    pass
