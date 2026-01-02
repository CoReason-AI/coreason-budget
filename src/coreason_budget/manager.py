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

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.guard import BudgetGuard
from coreason_budget.ledger import RedisLedger
from coreason_budget.pricing import PricingEngine


class BudgetManager:
    """
    Main entry point for Coreason Budget.
    Orchestrates BudgetGuard, RedisLedger, and PricingEngine.
    """

    def __init__(self, config: CoreasonBudgetConfig) -> None:
        self.config = config
        self.ledger = RedisLedger(config.redis_url)
        self.pricing = PricingEngine(config)
        self.guard = BudgetGuard(config, self.ledger)

    async def check_availability(
        self, user_id: str, project_id: Optional[str] = None, estimated_cost: float = 0.0
    ) -> None:
        """
        Pre-flight check: Verify if budget allows the request.
        Raises BudgetExceededError if limit reached.
        """
        await self.guard.check_availability(user_id, project_id, estimated_cost=estimated_cost)

    async def record_spend(
        self, user_id: str, amount: float, project_id: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        """
        Post-flight charge: Record the actual spend.
        """
        await self.guard.record_spend(user_id, amount, project_id, model=model)

    async def close(self) -> None:
        """Cleanup resources (Redis connection)."""
        await self.ledger.close()
