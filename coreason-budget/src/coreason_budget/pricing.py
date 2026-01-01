from decimal import Decimal
import litellm
from typing import Optional, Dict
from litellm.types.utils import ModelResponse, Usage

class PricingEngine:
    """
    Component A: PricingEngine (The Actuary)
    Calculates the USD cost of a transaction using liteLLM.
    Supports overrides via configuration.
    """

    def __init__(self, custom_prices: Optional[Dict[str, Dict[str, float]]] = None):
        self.custom_prices = custom_prices or {}

    def calculate(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate the cost of a transaction.

        Args:
            model: The model name (e.g., 'gpt-4').
            input_tokens: Number of prompt tokens.
            output_tokens: Number of completion tokens.

        Returns:
            float: Cost in USD.
        """
        # Check for custom pricing
        if model in self.custom_prices:
            pricing = self.custom_prices[model]
            input_cost = pricing.get("input_cost_per_token", 0.0) * input_tokens
            output_cost = pricing.get("output_cost_per_token", 0.0) * output_tokens
            return input_cost + output_cost

        try:
            # completion_cost can take a completion_response object to calculate cost based on tokens
            # We construct a mock response object to pass the token counts.
            mock_response = ModelResponse(
                model=model,
                usage=Usage(
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens
                )
            )

            cost = litellm.completion_cost(completion_response=mock_response)
            return float(cost)
        except Exception as e:
            # Fallback or error handling could go here.
            # For now, we propagate the error.
            raise e
