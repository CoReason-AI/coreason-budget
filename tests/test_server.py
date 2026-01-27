import os
from typing import Generator
from unittest.mock import patch

import pytest
from fakeredis import aioredis
from fastapi.testclient import TestClient

from coreason_budget.server import app


# Fixture to provide a TestClient with mocked Redis
@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    # Create a fake redis instance
    fake_redis = aioredis.FakeRedis(decode_responses=True)

    # Patch from_url in ledger.py to return our fake redis
    # Patch os.environ to ensure configuration is valid
    env_patch = patch.dict(os.environ, {"COREASON_BUDGET_REDIS_URL": "redis://localhost:6379"})
    redis_patch = patch("coreason_budget.ledger.from_url", return_value=fake_redis)

    with env_patch, redis_patch:
        with TestClient(app) as c:
            yield c


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "redis": "connected"}


def test_check_budget_allowed(client: TestClient) -> None:
    # Default limit is $10.0 per user (from config default)
    response = client.post("/check", json={"user_id": "user_allow", "estimated_cost": 1.0})
    assert response.status_code == 200
    assert response.json() == {"status": "allowed"}


def test_check_budget_exceeded(client: TestClient) -> None:
    # Spend enough to exceed limit (limit=10)
    # First, record a spend of 11
    client.post("/spend", json={"user_id": "user_exceed", "cost": 11.0})

    # Now check
    response = client.post("/check", json={"user_id": "user_exceed", "estimated_cost": 1.0})
    assert response.status_code == 429
    assert "exceeded" in response.json()["detail"].lower()


def test_record_spend(client: TestClient) -> None:
    response = client.post("/spend", json={"user_id": "user_spend", "cost": 5.0})
    assert response.status_code == 200
    assert response.json() == {"status": "recorded"}

    # Verify usage increased
    # user_spend has 5.0 used. Limit is 10.0.
    # Try check 6.0 -> 5+6=11 > 10 -> fail
    response = client.post("/check", json={"user_id": "user_spend", "estimated_cost": 6.0})
    assert response.status_code == 429


def test_validation_error_pydantic(client: TestClient) -> None:
    # Missing user_id -> 422 Unprocessable Entity (Pydantic)
    response = client.post("/check", json={"estimated_cost": 1.0})
    assert response.status_code == 422


def test_validation_error_logic(client: TestClient) -> None:
    # Empty user_id -> 400 Bad Request (BudgetManager validation)
    response = client.post("/check", json={"user_id": "", "estimated_cost": 1.0})
    assert response.status_code == 400
    assert "user_id" in response.json()["detail"]


def test_record_spend_validation_error(client: TestClient) -> None:
    # Empty user_id -> 400 Bad Request (BudgetManager validation)
    response = client.post("/spend", json={"user_id": "", "cost": 5.0})
    assert response.status_code == 400
    assert "user_id" in response.json()["detail"]


def test_health_check_failure(client: TestClient) -> None:
    # We need to simulate a Redis failure.
    # We can patch the ping method of the redis connection on the existing app.state.budget
    from redis.exceptions import ConnectionError

    # Get the budget manager from the app
    # Since TestClient runs in same process, we can access app.state
    # But client is a fixture. We can use the app object directly.
    budget = app.state.budget

    # Mock the ping method
    original_ping = budget._async_ledger._redis.ping

    async def side_effect() -> None:
        raise ConnectionError("Simulated failure")

    budget._async_ledger._redis.ping = side_effect

    try:
        response = client.get("/health")
        assert response.status_code == 503
        assert "Redis connection failed" in response.json()["detail"]
    finally:
        # Restore
        budget._async_ledger._redis.ping = original_ping
