import os
import json
from typing import Generator
from unittest.mock import patch, AsyncMock

import pytest
from fakeredis import aioredis
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from coreason_budget.server import app
from coreason_identity.models import UserContext


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

@pytest.fixture
def valid_context_header() -> dict[str, str]:
    context = UserContext(
        user_id="user_allow",
        email="user@example.com",
        groups=[],
        scopes=[],
        claims={}
    )
    return {"X-User-Context": context.model_dump_json()}

@pytest.fixture
def context_exceed() -> dict[str, str]:
    context = UserContext(
        user_id="user_exceed",
        email="exceed@example.com",
        groups=[],
        scopes=[],
        claims={}
    )
    return {"X-User-Context": context.model_dump_json()}

@pytest.fixture
def context_spend() -> dict[str, str]:
    context = UserContext(
        user_id="user_spend",
        email="spend@example.com",
        groups=[],
        scopes=[],
        claims={}
    )
    return {"X-User-Context": context.model_dump_json()}


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "redis": "connected"}


def test_check_budget_allowed(client: TestClient, valid_context_header: dict[str, str]) -> None:
    # Default limit is $10.0 per user
    # user_id in body is ignored, using context
    response = client.post(
        "/check",
        json={"estimated_cost": 1.0},
        headers=valid_context_header
    )
    assert response.status_code == 200
    assert response.json() == {"status": "allowed"}


def test_check_budget_exceeded(client: TestClient, context_exceed: dict[str, str]) -> None:
    # Spend enough to exceed limit (limit=10)
    # First, record a spend of 11
    client.post(
        "/spend",
        json={"cost": 11.0},
        headers=context_exceed
    )

    # Now check
    response = client.post(
        "/check",
        json={"estimated_cost": 1.0},
        headers=context_exceed
    )
    assert response.status_code == 429
    assert "exceeded" in response.json()["detail"].lower()


def test_record_spend(client: TestClient, context_spend: dict[str, str]) -> None:
    response = client.post(
        "/spend",
        json={"cost": 5.0},
        headers=context_spend
    )
    assert response.status_code == 200
    assert response.json() == {"status": "recorded"}

    # Verify usage increased
    # user_spend has 5.0 used. Limit is 10.0.
    # Try check 6.0 -> 5+6=11 > 10 -> fail
    response = client.post(
        "/check",
        json={"estimated_cost": 6.0},
        headers=context_spend
    )
    assert response.status_code == 429


def test_missing_context(client: TestClient) -> None:
    response = client.post("/check", json={"estimated_cost": 1.0})
    assert response.status_code == 401
    assert "Missing User Context" in response.json()["detail"]


def test_invalid_context(client: TestClient) -> None:
    response = client.post(
        "/check",
        json={"estimated_cost": 1.0},
        headers={"X-User-Context": "invalid-json"}
    )
    assert response.status_code == 401
    assert "Invalid User Context" in response.json()["detail"]


def test_validation_error_logic(client: TestClient) -> None:
    # Empty user_id in context -> 400 Bad Request (BudgetManager validation)
    context = UserContext(
        user_id="",
        email="user@example.com",
        groups=[],
        scopes=[],
        claims={}
    )
    headers = {"X-User-Context": context.model_dump_json()}

    response = client.post(
        "/check",
        json={"estimated_cost": 1.0},
        headers=headers
    )
    assert response.status_code == 400
    assert "user_id" in response.json()["detail"]


def test_health_check_failure(client: TestClient) -> None:
    budget = app.state.budget
    original_ping = budget._async_ledger._redis.ping

    # Use AsyncMock to ensure it's awaited correctly and raises
    budget._async_ledger._redis.ping = AsyncMock(side_effect=ConnectionError("Simulated failure"))

    try:
        response = client.get("/health")
        assert response.status_code == 503
        assert "Redis connection failed" in response.json()["detail"]
    finally:
        budget._async_ledger._redis.ping = original_ping
