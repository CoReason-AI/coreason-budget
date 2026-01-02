# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import litellm

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.utils.logger import logger


class PricingEngine:
    """Calculates cost of LLM transactions using liteLLM."""

    def __init__(self, config: CoreasonBudgetConfig = None) -> None:
        """
        Initialize PricingEngine.

        Args:
            config: Optional configuration object. If provided, allows using custom model prices.
        """
        self.config = config or CoreasonBudgetConfig()

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
        # Check for custom overrides
        if self.config.custom_model_prices and model in self.config.custom_model_prices:
            prices = self.config.custom_model_prices[model]
            input_cost = prices.get("input_cost_per_token", 0.0)
            output_cost = prices.get("output_cost_per_token", 0.0)
            cost = (input_tokens * input_cost) + (output_tokens * output_cost)
            return cost

        try:
            # completion_cost returns float
            cost = litellm.completion_cost(model=model, prompt_tokens=input_tokens, completion_tokens=output_tokens)
            return float(cost)
        except Exception as e:
            logger.error("Failed to calculate cost for model {}: {}", model, e)
            raise
