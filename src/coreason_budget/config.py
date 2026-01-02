# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from typing import Dict

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelPrice(BaseModel):  # type: ignore[misc]
    """Cost configuration for a model."""

    input_cost_per_token: float = Field(description="Cost per input token in USD")
    output_cost_per_token: float = Field(description="Cost per output token in USD")


class CoreasonBudgetConfig(BaseSettings):  # type: ignore[misc]
    """Configuration for Coreason Budget."""

    model_config = SettingsConfigDict(env_prefix="COREASON_BUDGET_", env_file=".env", env_file_encoding="utf-8")

    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    daily_user_limit_usd: float = Field(default=10.0, description="Default daily spend limit per user in USD")
    daily_project_limit_usd: float = Field(default=500.0, description="Default daily spend limit per project in USD")
    daily_global_limit_usd: float = Field(default=5000.0, description="Global hard limit for daily spend in USD")

    model_price_overrides: Dict[str, ModelPrice] = Field(
        default_factory=dict, description="Custom pricing overrides by model name"
    )
