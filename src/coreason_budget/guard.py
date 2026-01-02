# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import datetime
from typing import List, Optional, Tuple

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.ledger import RedisLedger
from coreason_budget.utils.logger import logger


class BudgetExceededError(Exception):
    """Raised when a budget limit is exceeded."""

    pass


class BudgetGuard:
    """Enforces budget limits."""

    def __init__(self, config: CoreasonBudgetConfig, ledger: RedisLedger) -> None:
        self.config = config
        self.ledger = ledger

    def _get_date_str(self) -> str:
        """Get current UTC date string (YYYY-MM-DD)."""
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def _get_ttl_seconds(self) -> int:
        """Get seconds until next UTC midnight."""
        now = datetime.datetime.now(datetime.timezone.utc)
        tomorrow = now + datetime.timedelta(days=1)
        midnight = datetime.datetime(
            year=tomorrow.year, month=tomorrow.month, day=tomorrow.day, tzinfo=datetime.timezone.utc
        )
        return int((midnight - now).total_seconds())

    def _get_keys_and_limits(self, user_id: str, project_id: Optional[str] = None) -> List[Tuple[str, float, str]]:
        """
        Return list of (redis_key, limit_amount, scope_name).
        Scope hierarchy: Global -> Project -> User.
        """
        date_str = self._get_date_str()
        items = []

        # Global Limit
        global_key = f"spend:v1:global:{date_str}"
        items.append((global_key, self.config.daily_global_limit_usd, "Global"))

        # Project Limit
        if project_id:
            project_key = f"spend:v1:project:{project_id}:{date_str}"
            items.append((project_key, self.config.daily_project_limit_usd, f"Project {project_id}"))

        # User Limit
        user_key = f"spend:v1:user:{user_id}:{date_str}"
        items.append((user_key, self.config.daily_user_limit_usd, f"User {user_id}"))

        return items

    async def check_availability(
        self, user_id: str, project_id: Optional[str] = None, estimated_cost: float = 0.0
    ) -> None:
        """
        Check if budget is available.
        Raises BudgetExceededError if any limit is reached.
        """
        checks = self._get_keys_and_limits(user_id, project_id)

        for key, limit, scope in checks:
            used = await self.ledger.get_usage(key)
            # Fail if budget is already exhausted (used >= limit)
            # OR if this specific request would exceed the limit (used + est > limit)
            if used >= limit or (estimated_cost > 0 and used + estimated_cost > limit):
                logger.warning(
                    "Budget exceeded for {}: Used ${} + Est ${} > Limit ${}", scope, used, estimated_cost, limit
                )
                raise BudgetExceededError(f"{scope} daily limit of ${limit} reached.")

            # Log successful check for this scope (User scope is most relevant to log if we want per-user tracking)
            if "User" in scope:
                logger.info(
                    "Budget Check: {} | Used: ${} + Est: ${} / Limit: ${}", scope, used, estimated_cost, limit
                )

    async def record_spend(
        self, user_id: str, amount: float, project_id: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        """
        Record spend against all applicable scopes.
        Args:
            user_id: The user ID.
            amount: The amount to record.
            project_id: Optional project ID.
            model: Optional model name (for metrics).
        """
        keys_info = self._get_keys_and_limits(user_id, project_id)
        ttl = self._get_ttl_seconds()

        # We need to increment all keys.
        for key, _, _ in keys_info:
            await self.ledger.increment(key, amount, ttl=ttl)

        # Log metric event
        # Format: finops.spend.total (Counter, tagged by Model and Project)
        # We simulate a metric emission via structured logging
        project_tag = project_id if project_id else "none"
        model_tag = model if model else "unknown"

        logger.info(
            "METRIC: finops.spend.total | Amount: ${} | Tags: model={}, project={}, user={}",
            amount,
            model_tag,
            project_tag,
            user_id,
        )
