from typing import Dict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreasonBudgetConfig(BaseSettings):  # type: ignore
    """
    Configuration for the Coreason Budget system.
    """

    redis_url: str = Field(..., description="The Redis connection URL.")

    # Limits
    daily_global_limit_usd: float = Field(5000.0, description="Global daily hard limit in USD.")
    daily_project_limit_usd: float = Field(500.0, description="Default daily limit per project in USD.")
    daily_user_limit_usd: float = Field(10.0, description="Default daily limit per user in USD.")

    # Overrides
    model_price_overrides: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description=(
            "Overrides for model pricing. Key is model name, value is dict with "
            "'input_cost_per_token' and 'output_cost_per_token'."
        ),
    )

    # Environment variable handling
    model_config = SettingsConfigDict(
        env_prefix="COREASON_BUDGET_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Alias for ease of use
BudgetConfig = CoreasonBudgetConfig
