from unittest.mock import MagicMock, AsyncMock, patch
import os

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from coreason_budget.server import app, get_user_context
from coreason_identity.models import UserContext

@pytest.mark.asyncio
async def test_get_user_context_from_state() -> None:
    request = MagicMock(spec=Request)
    context = UserContext(
        user_id="state_user",
        email="state@example.com",
        groups=[],
        scopes=[],
        claims={}
    )
    request.state.user_context = context

    result = await get_user_context(request)
    assert result == context

@pytest.mark.asyncio
async def test_get_user_context_missing() -> None:
    request = MagicMock(spec=Request)
    request.state = MagicMock(spec=[]) # Empty state

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await get_user_context(request, x_user_context=None)
    assert exc.value.status_code == 401

def test_health_check_generic_exception() -> None:
    # Patch env BEFORE creating TestClient (which triggers lifespan -> Config init)
    with patch.dict(os.environ, {"COREASON_BUDGET_REDIS_URL": "redis://localhost:6379"}):
        # We also need to patch the ledger connection to avoid real connection attempt if any
        # But lifespan calls BudgetManager which creates RedisLedger.
        # RedisLedger creates Redis client (lazy).
        # We need to ensure connect() is mocked or not failing if it tries real redis.
        # However, server.py lifespan does NOT call connect(). It relies on lazy connection.
        # BUT health_check DOES call ping.

        # We need to patch from_url to return a mock or fake redis,
        # so that when we patch `ping` later, we are patching the right thing.
        from fakeredis import aioredis
        fake_redis = aioredis.FakeRedis(decode_responses=True)

        with patch("coreason_budget.ledger.from_url", return_value=fake_redis):
            with TestClient(app) as client:
                budget = app.state.budget
                # Now patch the ping method on the ledger's redis client
                original_ping = budget._async_ledger._redis.ping

                # Mock it to raise Exception
                budget._async_ledger._redis.ping = AsyncMock(side_effect=Exception("Generic failure"))

                try:
                    response = client.get("/health")
                    assert response.status_code == 503
                    assert "Redis connection failed" in response.json()["detail"]
                finally:
                    budget._async_ledger._redis.ping = original_ping
