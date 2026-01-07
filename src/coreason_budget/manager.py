from typing import Optional

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.guard import BudgetGuard, SyncBudgetGuard
from coreason_budget.ledger import RedisLedger, SyncRedisLedger
from coreason_budget.pricing import PricingEngine
from coreason_budget.validation import validate_check_availability_inputs, validate_record_spend_inputs


class BudgetManager:
    """
    Main interface for the Budget system.
    Supports both Async and Sync workflows via separate methods for check/charge,
    but primarily designed for async integration.
    """

    def __init__(self, config: CoreasonBudgetConfig):
        self.config = config

        # Async Components
        self._async_ledger = RedisLedger(config.redis_url)
        self.guard = BudgetGuard(config, self._async_ledger)

        # Sync Components
        self._sync_ledger = SyncRedisLedger(config.redis_url)
        self.sync_guard = SyncBudgetGuard(config, self._sync_ledger)

        self.pricing = PricingEngine(config)

    async def check_availability(
        self, user_id: str, project_id: Optional[str] = None, estimated_cost: float = 0.0
    ) -> bool:
        """
        Check budget availability asynchronously.
        """
        validate_check_availability_inputs(user_id)
        return await self.guard.check(user_id, project_id, estimated_cost)

    def check_availability_sync(
        self, user_id: str, project_id: Optional[str] = None, estimated_cost: float = 0.0
    ) -> bool:
        """
        Check budget availability synchronously.
        """
        validate_check_availability_inputs(user_id)
        return self.sync_guard.check(user_id, project_id, estimated_cost)

    async def record_spend(
        self, user_id: str, cost: float, project_id: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        """
        Record spend asynchronously.
        """
        validate_record_spend_inputs(user_id, cost, project_id, model)
        await self.guard.charge(user_id, cost, project_id, model)

    def record_spend_sync(
        self, user_id: str, cost: float, project_id: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        """
        Record spend synchronously.
        """
        validate_record_spend_inputs(user_id, cost, project_id, model)
        self.sync_guard.charge(user_id, cost, project_id, model)

    async def close(self) -> None:
        """
        Cleanup resources.
        """
        await self._async_ledger.close()
        self._sync_ledger.close()
