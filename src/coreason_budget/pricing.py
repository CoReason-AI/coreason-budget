import litellm

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.utils.logger import logger


class PricingEngine:
    """
    Calculates the cost of LLM transactions using liteLLM or configured overrides.
    """

    def __init__(self, config: CoreasonBudgetConfig) -> None:
        self.config = config

    def calculate(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Calculate the cost in USD for the given usage.
        Checks for overrides first, then falls back to liteLLM.
        """
        # 1. Check for overrides
        if model in self.config.model_price_overrides:
            override = self.config.model_price_overrides[model]
            input_cost_per_token = override.get("input_cost_per_token", 0.0)
            output_cost_per_token = override.get("output_cost_per_token", 0.0)

            cost = (input_tokens * input_cost_per_token) + (output_tokens * output_cost_per_token)
            logger.debug("Using override price for {}: ${}", model, cost)
            return float(cost)

        # 2. Use liteLLM
        try:
            # completion_cost returns float or Decimal? Usually float.
            # liteLLM docs say it returns cost as float.
            cost = litellm.completion_cost(
                model=model,
                prompt=None,  # We can pass tokens directly
                completion=None,
                total_input_tokens=input_tokens,
                total_output_tokens=output_tokens,
            )
            return float(cost)
        except Exception as e:
            logger.error("Failed to calculate cost for model {}: {}", model, e)
            raise ValueError(f"Could not calculate cost for model {model}: {e}") from e

    # Alias for backward compatibility if I had released it, but I haven't.
    # But for internal consistency or if I used it elsewhere in tests I might want to keep it or refactor.
    # I will refactor usages.
    calculate_cost = calculate
