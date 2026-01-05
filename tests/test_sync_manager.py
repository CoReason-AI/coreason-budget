# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from typing import Generator
from unittest import mock

import pytest
from fakeredis import FakeRedis

from coreason_budget import BudgetConfig, BudgetExceededError, SyncBudgetManager


@pytest.fixture
def sync_manager() -> Generator[SyncBudgetManager, None, None]:
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=10.0)
    mgr = SyncBudgetManager(config)

    # Inject fake redis
    mgr.ledger._redis = FakeRedis(decode_responses=True)

    yield mgr
    mgr.close()


def test_sync_manager_initialization(sync_manager: SyncBudgetManager) -> None:
    """Test proper initialization of SyncBudgetManager."""
    assert sync_manager.config.daily_user_limit_usd == 10.0
    assert sync_manager.ledger is not None
    assert sync_manager.guard is not None
    assert sync_manager.pricing is not None


def test_sync_check_availability_success(sync_manager: SyncBudgetManager) -> None:
    """Test successful budget check (synchronous)."""
    user_id = "test_user_sync"
    # Should not raise exception
    sync_manager.check_availability(user_id)
    # Check with estimated cost
    sync_manager.check_availability(user_id, estimated_cost=5.0)


def test_sync_record_spend(sync_manager: SyncBudgetManager) -> None:
    """Test recording spend (synchronous)."""
    user_id = "test_user_sync"
    amount = 2.5

    sync_manager.record_spend(user_id, amount)

    # Verify via ledger
    date_str = sync_manager.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"

    usage = sync_manager.ledger.get_usage(key)
    assert usage == 2.5


def test_sync_budget_exceeded(sync_manager: SyncBudgetManager) -> None:
    """Test budget exceeded exception (synchronous)."""
    user_id = "test_user_sync_exceed"
    limit = sync_manager.config.daily_user_limit_usd

    # Use up the budget
    sync_manager.record_spend(user_id, limit)

    # Try to check availability
    with pytest.raises(BudgetExceededError):
        sync_manager.check_availability(user_id, estimated_cost=1.0)


def test_sync_budget_exceeded_with_estimate(sync_manager: SyncBudgetManager) -> None:
    """Test budget exceeded via estimate (synchronous)."""
    user_id = "test_user_sync_est"
    limit = sync_manager.config.daily_user_limit_usd

    # Half used
    sync_manager.record_spend(user_id, limit / 2)

    # Check that would push over limit
    with pytest.raises(BudgetExceededError):
        sync_manager.check_availability(user_id, estimated_cost=(limit / 2) + 1.0)


def test_sync_ledger_ttl(sync_manager: SyncBudgetManager) -> None:
    """Test that TTL is set correctly in synchronous ledger."""
    user_id = "test_user_ttl"
    sync_manager.record_spend(user_id, 1.0)

    date_str = sync_manager.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"

    ttl = sync_manager.ledger._redis.ttl(key)
    # Just verify TTL is set (positive integer)
    assert ttl > 0


def test_sync_manager_input_validation(sync_manager: SyncBudgetManager) -> None:
    """Test input validation for synchronous manager."""
    with pytest.raises(ValueError):
        sync_manager.check_availability("")

    with pytest.raises(ValueError):
        sync_manager.record_spend("", 1.0)

    with pytest.raises(ValueError):
        sync_manager.record_spend("user", float("inf"))

    with pytest.raises(ValueError):
        sync_manager.record_spend("user", 1.0, project_id=" ")

    with pytest.raises(ValueError):
        sync_manager.record_spend("user", 1.0, model=" ")


def test_sync_connection_error() -> None:
    """Test connection error handling in synchronous mode."""
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = SyncBudgetManager(config)

    from redis.exceptions import ConnectionError as RedisConnectionError

    # Mock redis to raise ConnectionError on ping
    with mock.patch("redis.Redis.ping", side_effect=RedisConnectionError("Connection failed")):
        # ledger.connect() calls ping()
        # But Manager.__init__ doesn't call connect() automatically,
        # let's try calling it manually if we exposed it, or just use check_availability
        # SyncRedisLedger uses lazy connection, but we can verify connect() behavior
        with pytest.raises(RedisConnectionError):
            mgr.ledger.connect()


def test_sync_connect_success(sync_manager: SyncBudgetManager) -> None:
    """Test successful connection verification."""
    # This calls ping() which should succeed with FakeRedis
    sync_manager.ledger.connect()


def test_sync_close_manual() -> None:
    """Test closing resources (manual creation)."""
    config = BudgetConfig(redis_url="redis://localhost:6379")
    mgr = SyncBudgetManager(config)
    mgr.ledger._redis = FakeRedis(decode_responses=True)

    # Just verify it doesn't crash
    mgr.close()

    # Verify we can't usage it easily after close if it were real,
    # but fakeredis might not care.
    # We mainly want to cover the lines.


def test_sync_ledger_errors(sync_manager: SyncBudgetManager) -> None:
    """Test error handling in SyncRedisLedger."""
    from redis.exceptions import RedisError

    # Mock get to raise RedisError
    with mock.patch.object(sync_manager.ledger._redis, "get", side_effect=RedisError("Get failed")):
        with pytest.raises(RedisError):
            sync_manager.ledger.get_usage("some_key")

    # Mock eval to raise RedisError (for increment)
    with mock.patch.object(sync_manager.ledger._redis, "eval", side_effect=RedisError("Eval failed")):
        with pytest.raises(RedisError):
            sync_manager.ledger.increment("some_key", 1.0)
