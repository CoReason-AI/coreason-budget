from datetime import datetime, timezone
from typing import Optional

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError
from coreason_budget.ledger import RedisLedger, SyncRedisLedger
from coreason_budget.utils.logger import logger


class BaseBudgetGuard:
    """Base logic for BudgetGuard (Sync and Async)."""

    def __init__(self, config: CoreasonBudgetConfig):
        self.config = config

    def _get_date_str(self) -> str:
        """Get current date string (UTC) for key construction."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _get_keys(self, user_id: str, project_id: Optional[str] = None) -> dict[str, str]:
        """Construct Redis keys for different scopes."""
        date_str = self._get_date_str()
        keys = {
            "global": f"budget:global:{date_str}",
            "user": f"budget:user:{user_id}:{date_str}",
        }
        if project_id:
            keys["project"] = f"budget:project:{project_id}:{date_str}"
        return keys

    def _calculate_ttl(self) -> int:
        """
        Calculate seconds until next UTC midnight.
        This ensures keys expire automatically.
        """
        now = datetime.now(timezone.utc)
        # Midnight next day
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
        current = now.timestamp()
        return int(midnight - current)


class BudgetGuard(BaseBudgetGuard):
    """Async Enforcer of budget limits."""

    def __init__(self, config: CoreasonBudgetConfig, ledger: RedisLedger):
        super().__init__(config)
        self.ledger = ledger

    async def check(self, user_id: str, project_id: Optional[str] = None, estimated_cost: float = 0.0) -> bool:
        """
        Check if the request allows for the estimated cost.
        Raises BudgetExceededError if limit would be breached.
        """
        keys = self._get_keys(user_id, project_id)

        # 1. Global Check
        global_usage = await self.ledger.get_usage(keys["global"])
        if global_usage + estimated_cost > self.config.daily_global_limit_usd:
            logger.warning(
                "Global budget exceeded. Used: ${}, Limit: ${}", global_usage, self.config.daily_global_limit_usd
            )
            raise BudgetExceededError("Global daily limit exceeded")

        # 2. Project Check
        if project_id and "project" in keys:
            project_usage = await self.ledger.get_usage(keys["project"])
            if project_usage + estimated_cost > self.config.daily_project_limit_usd:
                logger.warning(
                    "Project budget exceeded. Project: {}, Used: ${}, Limit: ${}",
                    project_id,
                    project_usage,
                    self.config.daily_project_limit_usd,
                )
                raise BudgetExceededError(f"Project daily limit exceeded for {project_id}")

        # 3. User Check
        user_usage = await self.ledger.get_usage(keys["user"])
        if user_usage + estimated_cost > self.config.daily_user_limit_usd:
            logger.warning(
                "User budget exceeded. User: {}, Used: ${}, Limit: ${}",
                user_id,
                user_usage,
                self.config.daily_user_limit_usd,
            )
            raise BudgetExceededError(f"User daily limit exceeded for {user_id}")

        # Success Log with details
        logger.info(
            "Budget Check Passed: User {} | Estimated Cost: ${} | Global Used: ${} | User Used: ${}",
            user_id,
            estimated_cost,
            global_usage,
            user_usage,
        )
        return True

    async def charge(
        self, user_id: str, cost: float, project_id: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        """
        Record actual spend.
        Updates counters for all scopes.
        """
        keys = self._get_keys(user_id, project_id)
        ttl = self._calculate_ttl()

        for key in keys.values():
            await self.ledger.increment(key, cost, ttl)

        # Observability
        logger.info(
            "Transaction Recorded",
            extra={
                "event": "finops.spend.total",
                "user_id": user_id,
                "project_id": project_id,
                "model": model,
                "cost_usd": cost,
            },
        )
        logger.info("Recorded Spend: User {} | Cost: ${} | Project: {} | Model: {}", user_id, cost, project_id, model)


class SyncBudgetGuard(BaseBudgetGuard):
    """Synchronous Enforcer of budget limits."""

    def __init__(self, config: CoreasonBudgetConfig, ledger: SyncRedisLedger):
        super().__init__(config)
        self.ledger = ledger

    def check(self, user_id: str, project_id: Optional[str] = None, estimated_cost: float = 0.0) -> bool:
        keys = self._get_keys(user_id, project_id)

        global_usage = self.ledger.get_usage(keys["global"])
        if global_usage + estimated_cost > self.config.daily_global_limit_usd:
            logger.warning(
                "Global budget exceeded. Used: ${}, Limit: ${}", global_usage, self.config.daily_global_limit_usd
            )
            raise BudgetExceededError("Global daily limit exceeded")

        if project_id and "project" in keys:
            project_usage = self.ledger.get_usage(keys["project"])
            if project_usage + estimated_cost > self.config.daily_project_limit_usd:
                logger.warning(
                    "Project budget exceeded. Project: {}, Used: ${}, Limit: ${}",
                    project_id,
                    project_usage,
                    self.config.daily_project_limit_usd,
                )
                raise BudgetExceededError(f"Project daily limit exceeded for {project_id}")

        user_usage = self.ledger.get_usage(keys["user"])
        if user_usage + estimated_cost > self.config.daily_user_limit_usd:
            logger.warning(
                "User budget exceeded. User: {}, Used: ${}, Limit: ${}",
                user_id,
                user_usage,
                self.config.daily_user_limit_usd,
            )
            raise BudgetExceededError(f"User daily limit exceeded for {user_id}")

        logger.info(
            "Budget Check Passed: User {} | Estimated Cost: ${} | Global Used: ${} | User Used: ${}",
            user_id,
            estimated_cost,
            global_usage,
            user_usage,
        )
        return True

    def charge(self, user_id: str, cost: float, project_id: Optional[str] = None, model: Optional[str] = None) -> None:
        keys = self._get_keys(user_id, project_id)
        ttl = self._calculate_ttl()

        for key in keys.values():
            self.ledger.increment(key, cost, ttl)

        logger.info(
            "Transaction Recorded",
            extra={
                "event": "finops.spend.total",
                "user_id": user_id,
                "project_id": project_id,
                "model": model,
                "cost_usd": cost,
            },
        )
        logger.info("Recorded Spend: User {} | Cost: ${} | Project: {} | Model: {}", user_id, cost, project_id, model)
