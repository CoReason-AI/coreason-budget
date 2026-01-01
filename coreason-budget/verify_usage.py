import asyncio
from coreason_budget import BudgetManager, BudgetConfig, BudgetExceededError
import fakeredis
import litellm

# Mock pricing to avoid API calls or issues with pricing data
# But since we use litellm.completion_cost which might need internet or pricing file
# We will just assume it works or mock it if needed.
# We already tested it works with a mock response object in test_budget.py.

async def main():
    print("Initializing Budget Manager...")
    # Using fakeredis connection string won't work with real redis client unless we patch it
    # But we can pass a fake client if the library allowed injection, but it takes a URL.
    # So we will patch the ledger after init, similar to tests.

    config = BudgetConfig(redis_url="redis://localhost:6379", default_daily_user_limit_usd=50.0)
    budget = BudgetManager(config)

    # Patch for verification without real redis
    server = fakeredis.FakeServer()
    budget.ledger.redis = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    user_id = "user_123"

    print("\n--- Pre-Flight Check ---")
    try:
        await budget.check_availability(user_id)
        print(f"Check passed for {user_id}")
    except BudgetExceededError:
        print(f"Check failed for {user_id}")
        return

    print("\n--- Simulate LLM Call ---")
    # Simulate LLM response
    model = "gpt-3.5-turbo"
    input_tokens = 50
    output_tokens = 50
    print(f"Model: {model}, Input: {input_tokens}, Output: {output_tokens}")

    print("\n--- Post-Flight Charge ---")
    try:
        cost = budget.pricing.calculate(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
        print(f"Calculated cost: ${cost}")

        await budget.record_spend(user_id, cost)
        print(f"Recorded spend for {user_id}")

    except Exception as e:
        print(f"Error recording spend: {e}")

    # Verify spend
    # We can peek into ledger if we want, but we trust the record_spend worked if no error.

    print("\n--- Done ---")
    await budget.close()

if __name__ == "__main__":
    asyncio.run(main())
