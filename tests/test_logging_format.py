import re
import pytest
from unittest.mock import MagicMock, patch
from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.guard import BudgetGuard
from coreason_budget.ledger import RedisLedger

@pytest.mark.asyncio
async def test_strict_logging_format():
    """Verify that logging strictly matches the required format: 'Budget Check: User [ID] | Used: $[X] / Limit: $[Y]'."""
    config = CoreasonBudgetConfig(daily_user_limit_usd=10.0)

    # Mock ledger to return a specific usage
    mock_ledger = MagicMock(spec=RedisLedger)
    # Make get_usage return an awaitable
    async def get_usage_side_effect(key: str) -> float:
        return 5.50
    mock_ledger.get_usage.side_effect = get_usage_side_effect

    guard = BudgetGuard(config, mock_ledger)

    user_id = "test_user_123"

    # Patch the logger
    with patch("coreason_budget.guard.logger") as mock_logger:
        await guard.check_availability(user_id)

        # Verify the log call
        # We expect a call like: logger.info("Budget Check: {} | Used: ${} / Limit: ${}", scope, used, limit)
        # where scope is "User test_user_123"

        # Filter calls for the specific message format
        relevant_calls = [
            call for call in mock_logger.info.call_args_list
            if "Budget Check:" in call.args[0]
        ]

        assert len(relevant_calls) > 0, "No relevant log call found"

        call_args = relevant_calls[0].args
        msg_template = call_args[0]
        args = call_args[1:]

        # Reconstruct the message
        # The code uses logger.info(msg, *args) style
        # But loguru uses {} style formatting.
        # We can simulate formatting to check the final string
        final_msg = msg_template.format(*args)

        # Expected regex
        # Budget Check: User test_user_123 | Used: $5.5 / Limit: $10.0
        pattern = r"^Budget Check: User .+ \| Used: \$\d+(\.\d+)? / Limit: \$\d+(\.\d+)?$"

        assert re.match(pattern, final_msg), f"Log message '{final_msg}' does not match pattern '{pattern}'"
        assert f"User {user_id}" in final_msg
        assert "Used: $5.5" in final_msg
        assert "Limit: $10.0" in final_msg
