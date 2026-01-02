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

import litellm

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.utils.logger import logger


class PricingEngine:
    """Calculates cost of LLM transactions using liteLLM."""

    def __init__(self, config: Optional[CoreasonBudgetConfig] = None) -> None:
        self.config = config

    def calculate(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost in USD for a given model and token usage.

        Args:
            model: The model name (e.g., 'gpt-4').
            input_tokens: Number of prompt tokens.
            output_tokens: Number of completion tokens.

        Returns:
            Cost in USD.
        """
        # Check for overrides
        if self.config and model in self.config.model_price_overrides:
            price = self.config.model_price_overrides[model]
            cost = (input_tokens * price.input_cost_per_token) + (output_tokens * price.output_cost_per_token)
            logger.info("Using override pricing for model {}: ${}", model, cost)
            return cost

        try:
            # completion_cost returns float
            cost = litellm.completion_cost(model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens)
            return float(cost)
        except Exception as e:
            # Fallback or error?
            # Prompt says "Fallback: Allow strictly typed overrides via configuration".
            # "Rejects requests (Circuit Breaking) when limits are exceeded."
            # If we can't calculate cost, we probably shouldn't charge 0.
            # But cost calculation happens Post-Flight.
            # If we fail to calculate cost, we fail to track spend.
            logger.error("Failed to calculate cost for model {}: {}", model, e)
            # For now, let's propagate the error so the caller knows something went wrong.
            raise
