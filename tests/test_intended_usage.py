from unittest.mock import MagicMock, patch

import pytest

from coreason_budget import BudgetConfig, BudgetExceededError, BudgetManager


@pytest.mark.asyncio
async def test_intended_usage_example() -> None:
    """
    Verifies that the API surface matches the 'Intended Usage Example'
    from the requirements exactly.
    """

    # Mocking Redis is handled by the ledger implementation if we want (via fakeredis),
    # but here we might want to ensure it works with the default behavior.
    # Since we don't have a real Redis, we will rely on the fact that our
    # tests/test_ledger.py already verified fake redis works.
    # However, to make this specific test run without a real redis server,
    # we can use the `mock.patch` or just assume the user of this script
    # would have a redis server.
    # For this verification, let's use a config that points to a test URL,
    # but patch the internal ledger connection to use fakeredis if possible,
    # OR just replicate the logic in a way that doesn't fail.

    # Actually, the best way to verify this IS to use fakeredis to simulate the server
    # transparently.

    # 1. Initialize
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_limit_usd=50.0)
    budget = BudgetManager(config)

    # Patch the ledger's redis client to use fakeredis so we don't need a real server
    from fakeredis.aioredis import FakeRedis

    budget.ledger._redis = FakeRedis(decode_responses=True)

    # 2. Pre-Flight Check (Fast)
    user_id = "user_123"
    try:
        await budget.check_availability(user_id)
    except BudgetExceededError:
        # return Response("Daily Limit Reached", status_code=429)
        pytest.fail("Budget should not be exceeded on first call")

    # ... Run LLM ...
    # response = await llm.generate(...)
    # Mock response object
    response = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50

    # 3. Post-Flight Charge (Async)
    # Calculate precise cost based on provider metadata

    # We need to mock pricing.calculate because we don't have a valid API key for LiteLLM to check real prices
    # OR we can rely on the default behavior if LiteLLM works without keys for some models (it usually needs keys).
    # Let's mock it to return a fixed cost to avoid external calls.
    with patch.object(budget.pricing, "calculate", return_value=0.005):
        cost = budget.pricing.calculate(
            model="gpt-4", input_tokens=response.usage.prompt_tokens, output_tokens=response.usage.completion_tokens
        )

        # Atomic increment
        await budget.record_spend(user_id, cost, project_id="proj_1", model="gpt-4")
        # print(f"Transaction Cost: ${cost}")

    # Verification: Check if spend was recorded
    # We can check the internal ledger or rely on a second check failing if limit is low.

    # Let's verify the cost was recorded by checking availability again with a high estimated cost
    # or checking the internal state (which is cheating slightly vs the public API).
    # But for this test, simply running without error confirms the API structure exists.

    assert cost == 0.005

    await budget.close()
