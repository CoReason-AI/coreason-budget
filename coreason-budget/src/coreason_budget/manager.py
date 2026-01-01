from typing import Optional
from datetime import datetime, timezone
import logging
from .config import BudgetConfig
from .ledger import RedisLedger
from .pricing import PricingEngine
from .exceptions import BudgetExceededError

# Configure logger
logger = logging.getLogger("coreason_budget")
# Ensure we have a handler if not configured by app
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class BudgetManager:
    """
    Component C: BudgetGuard (The Enforcer)
    Coordinates budget checks and recording.
    """

    def __init__(self, config: BudgetConfig):
        self.config = config
        self.ledger = RedisLedger(config.redis_url)
        self.pricing = PricingEngine(custom_prices=config.custom_model_prices)

    async def check_availability(self, user_id: str, project_id: Optional[str] = None):
        """
        Pre-Flight Check: Checks if the user/project has remaining budget.
        Uses a heuristic or checks current spend vs limit.
        """
        # We check daily limits.
        # Key format: spend:v1:{scope}:{id}:{date}
        # Use timezone aware UTC
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. Global Hard Limit
        global_key = f"spend:v1:global:{date_str}"
        global_spend = await self.ledger.get_current_usage(global_key)

        # Log check
        # Requirement: Log: "Budget Check: User [ID] | Used: $[X] / Limit: $[Y]"
        # Since we check multiple limits, we log relevant ones or the one that fails?
        # Let's log user check primarily as per req example.

        if global_spend >= self.config.global_daily_limit_usd:
            logger.warning(f"Budget Check Failed: Global Limit | Used: ${global_spend} / Limit: ${self.config.global_daily_limit_usd}")
            raise BudgetExceededError(f"Global daily limit of ${self.config.global_daily_limit_usd} reached.")

        # 2. User Limit
        user_key = f"spend:v1:user:{user_id}:{date_str}"
        user_spend = await self.ledger.get_current_usage(user_key)

        logger.info(f"Budget Check: User {user_id} | Used: ${user_spend} / Limit: ${self.config.default_daily_user_limit_usd}")

        if user_spend >= self.config.default_daily_user_limit_usd:
            raise BudgetExceededError(f"User daily limit of ${self.config.default_daily_user_limit_usd} reached for user {user_id}.")

        # 3. Project Limit (if applicable)
        if project_id:
            project_key = f"spend:v1:project:{project_id}:{date_str}"
            project_spend = await self.ledger.get_current_usage(project_key)

            logger.info(f"Budget Check: Project {project_id} | Used: ${project_spend} / Limit: ${self.config.default_daily_project_limit_usd}")

            if project_spend >= self.config.default_daily_project_limit_usd:
                raise BudgetExceededError(f"Project daily limit of ${self.config.default_daily_project_limit_usd} reached for project {project_id}.")

    async def record_spend(self, user_id: str, cost: float, project_id: Optional[str] = None, model: Optional[str] = None):
        """
        Post-Flight Charge: Record the actual cost.
        """
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Increment Global
        global_key = f"spend:v1:global:{date_str}"
        await self.ledger.increment(global_key, cost)

        # Increment User
        user_key = f"spend:v1:user:{user_id}:{date_str}"
        await self.ledger.increment(user_key, cost)

        # Increment Project
        if project_id:
            project_key = f"spend:v1:project:{project_id}:{date_str}"
            await self.ledger.increment(project_key, cost)

        # Metric: finops.spend.total (Counter, tagged by Model and Project)
        # We simulate metric emission via log for now as no metric lib is specified.
        # "Metric: finops.spend.total (Counter, tagged by Model and Project)"
        metric_tags = f"model={model or 'unknown'}, project={project_id or 'none'}"
        logger.info(f"Metric: finops.spend.total value={cost} tags=[{metric_tags}]")

    async def close(self):
        await self.ledger.close()
