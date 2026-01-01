from pydantic import BaseModel, Field
from typing import Dict, Optional

class BudgetConfig(BaseModel):
    """Configuration for the Budget Manager."""
    redis_url: str = Field(..., description="Redis connection URL")
    default_daily_user_limit_usd: float = Field(10.0, description="Default daily limit per user in USD")
    default_daily_project_limit_usd: float = Field(50.0, description="Default daily limit per project in USD")
    global_daily_limit_usd: float = Field(5000.0, description="Global daily hard limit for the platform in USD")

    # Pricing overrides: model_name -> cost_per_token (simplified) or cost multiplier
    # Requirement: "Strictly typed overrides via configuration"
    # litellm returns total cost. If we want to override, we might need cost per 1k tokens or similar.
    # But for simplicity and to match "negotiated rate", let's allow a multiplier or fixed price map.
    # However, litellm calculates based on input/output.
    # Let's add a dictionary for custom pricing: model -> {input_cost_per_token, output_cost_per_token}
    # Or simpler: just let PricingEngine handle it if we pass this config to it.
    custom_model_prices: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description="Custom pricing per model. Key is model name, value is dict with 'input_cost_per_token' and 'output_cost_per_token'."
    )
