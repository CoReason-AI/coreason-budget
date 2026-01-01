import pytest
import pytest_asyncio
import logging
from coreason_budget.config import BudgetConfig
from coreason_budget.manager import BudgetManager
from coreason_budget.pricing import PricingEngine
from coreason_budget.exceptions import BudgetExceededError
import fakeredis

@pytest.fixture
def mock_redis():
    server = fakeredis.FakeServer()
    # Mock redis connection url
    return "redis://localhost:6379"

@pytest.fixture
def budget_config(mock_redis):
    return BudgetConfig(
        redis_url=mock_redis,
        default_daily_user_limit_usd=10.0,
        default_daily_project_limit_usd=50.0,
        global_daily_limit_usd=100.0,
        custom_model_prices={
            "custom-model": {
                "input_cost_per_token": 0.001,
                "output_cost_per_token": 0.002
            }
        }
    )

@pytest_asyncio.fixture
async def budget_manager(budget_config):
    manager = BudgetManager(budget_config)
    # Patch RedisLedger.redis
    server = fakeredis.FakeServer()
    manager.ledger.redis = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    yield manager
    await manager.close()

@pytest.mark.asyncio
async def test_pricing_engine():
    engine = PricingEngine()
    cost = engine.calculate("gpt-3.5-turbo", 100, 100)
    assert isinstance(cost, float)
    assert cost > 0

@pytest.mark.asyncio
async def test_pricing_engine_custom_price():
    custom_prices = {
        "my-model": {
            "input_cost_per_token": 0.01,
            "output_cost_per_token": 0.02
        }
    }
    engine = PricingEngine(custom_prices=custom_prices)

    # 10 input * 0.01 = 0.1
    # 10 output * 0.02 = 0.2
    # Total = 0.3
    cost = engine.calculate("my-model", 10, 10)
    assert cost == pytest.approx(0.3)

    # Fallback to litellm for unknown model
    cost_gpt = engine.calculate("gpt-3.5-turbo", 100, 100)
    assert cost_gpt > 0

@pytest.mark.asyncio
async def test_budget_manager_check_and_charge(budget_manager, caplog):
    user_id = "user_123"

    with caplog.at_level(logging.INFO):
        # 1. Check availability - should pass
        await budget_manager.check_availability(user_id)
        assert f"Budget Check: User {user_id}" in caplog.text

        # 2. Charge some amount
        cost = 5.0
        await budget_manager.record_spend(user_id, cost, model="gpt-4")
        assert "Metric: finops.spend.total value=5.0" in caplog.text

        # 3. Check availability again
        await budget_manager.check_availability(user_id)

        # 4. Charge more to exceed limit
        await budget_manager.record_spend(user_id, 6.0) # Total 11.0

        # 5. Check availability - should fail
        with pytest.raises(BudgetExceededError):
            await budget_manager.check_availability(user_id)

@pytest.mark.asyncio
async def test_global_limit(budget_manager):
    user_id = "user_global"
    await budget_manager.record_spend(user_id, 101.0)

    with pytest.raises(BudgetExceededError) as excinfo:
        await budget_manager.check_availability("any_user")
    assert "Global daily limit" in str(excinfo.value)

@pytest.mark.asyncio
async def test_project_limit(budget_manager):
    user_id = "user_proj"
    project_id = "proj_1"

    await budget_manager.record_spend(user_id, 40.0, project_id=project_id)

    budget_manager.config.default_daily_user_limit_usd = 100.0

    await budget_manager.check_availability(user_id, project_id=project_id)

    await budget_manager.record_spend(user_id, 11.0, project_id=project_id)

    with pytest.raises(BudgetExceededError) as excinfo:
        await budget_manager.check_availability(user_id, project_id=project_id)
    assert "Project daily limit" in str(excinfo.value)
