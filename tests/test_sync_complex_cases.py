# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fakeredis import FakeRedis

from coreason_budget import BudgetConfig, SyncBudgetManager


@pytest.fixture
def sync_manager_complex() -> SyncBudgetManager:
    config = BudgetConfig(redis_url="redis://localhost:6379", daily_user_limit_usd=100.0)
    mgr = SyncBudgetManager(config)
    mgr.ledger._redis = FakeRedis(decode_responses=True)
    return mgr


def test_sync_partial_failure_consistency(sync_manager_complex: SyncBudgetManager) -> None:
    """
    Test partial failure: Global succeeds, Project fails.
    Verifies that the exception propagates and state is partially updated.
    """
    user_id = "user_sync_partial"
    project_id = "proj_sync_partial"

    # Save original method
    original_increment = sync_manager_complex.ledger.increment

    def side_effect(key: str, amount: float, ttl: int | None = None) -> float:
        if "global" in key:
            return original_increment(key, amount, ttl)
        if "project" in key:
            raise RuntimeError("Redis Failed Sync Halfway")
        return original_increment(key, amount, ttl)

    with patch.object(sync_manager_complex.ledger, "increment", side_effect=side_effect):
        with pytest.raises(RuntimeError, match="Redis Failed Sync Halfway"):
            sync_manager_complex.record_spend(user_id, 1.0, project_id=project_id)

    # Verify State
    date_str = sync_manager_complex.guard._get_date_str()
    global_key = f"spend:v1:global:{date_str}"
    project_key = f"spend:v1:project:{project_id}:{date_str}"
    user_key = f"spend:v1:user:{user_id}:{date_str}"

    global_usage = sync_manager_complex.ledger.get_usage(global_key)
    project_usage = sync_manager_complex.ledger.get_usage(project_key)
    user_usage = sync_manager_complex.ledger.get_usage(user_key)

    assert global_usage == 1.0
    assert project_usage == 0.0
    assert user_usage == 0.0


def test_sync_ttl_persistence(sync_manager_complex: SyncBudgetManager) -> None:
    """
    Verify that TTL is set on first write and NOT reset on subsequent writes.
    """
    user_id = "user_sync_ttl"
    date_str = sync_manager_complex.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"

    # First write: TTL should be set.
    fixed_ttl = 3600
    with patch.object(sync_manager_complex.guard, "_get_ttl_seconds", return_value=fixed_ttl):
        sync_manager_complex.record_spend(user_id, 10.0)

    actual_ttl = sync_manager_complex.ledger._redis.ttl(key)
    assert actual_ttl > 0
    assert actual_ttl <= fixed_ttl

    # Second write: Simulate later time with shorter calculated TTL.
    # Existing TTL should be preserved.
    short_ttl = 100
    with patch.object(sync_manager_complex.guard, "_get_ttl_seconds", return_value=short_ttl):
        sync_manager_complex.record_spend(user_id, 10.0)

    actual_ttl_after = sync_manager_complex.ledger._redis.ttl(key)

    # Should stay close to 3600, NOT drop to 100
    assert actual_ttl_after > 3000
    assert actual_ttl_after <= 3600


def test_sync_clock_skew(sync_manager_complex: SyncBudgetManager) -> None:
    """Test behavior when machine time shifts (writes to correct date keys)."""
    user_id = "user_sync_time"

    # Time 1: Today
    with patch.object(sync_manager_complex.guard, "_get_date_str", return_value="2025-01-01"):
        sync_manager_complex.record_spend(user_id, 10.0)
        assert sync_manager_complex.ledger.get_usage("spend:v1:user:user_sync_time:2025-01-01") == 10.0

    # Time 2: Tomorrow
    with patch.object(sync_manager_complex.guard, "_get_date_str", return_value="2025-01-02"):
        sync_manager_complex.record_spend(user_id, 5.0)
        assert sync_manager_complex.ledger.get_usage("spend:v1:user:user_sync_time:2025-01-02") == 5.0

    # Time 3: Back to Today
    with patch.object(sync_manager_complex.guard, "_get_date_str", return_value="2025-01-01"):
        sync_manager_complex.record_spend(user_id, 5.0)
        assert sync_manager_complex.ledger.get_usage("spend:v1:user:user_sync_time:2025-01-01") == 15.0


def test_sync_zero_negative_spend(sync_manager_complex: SyncBudgetManager) -> None:
    """Test 0.0 and negative spend (refunds)."""
    user_id = "user_sync_free"

    # Record 0
    sync_manager_complex.record_spend(user_id, 0.0)

    # Verify limits (User is 2nd item if no project)
    # Global -> User
    items = sync_manager_complex.guard._get_keys_and_limits(user_id)
    assert len(items) == 2
    assert items[1][1] == 100.0  # Limit is 100

    # Record spend
    sync_manager_complex.record_spend(user_id, 50.0)

    # Record negative (refund)
    sync_manager_complex.record_spend(user_id, -20.0)

    date_str = sync_manager_complex.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"
    usage = sync_manager_complex.ledger.get_usage(key)

    assert usage == 30.0  # 50 - 20


def test_sync_concurrency_race(sync_manager_complex: SyncBudgetManager) -> None:
    """
    Test concurrent access using threads.
    SyncBudgetManager methods are thread-safe (assuming Redis client is).
    """
    user_id = "user_sync_race"
    iterations = 20

    def task() -> bool:
        try:
            sync_manager_complex.check_availability(user_id, estimated_cost=1.0)
            sync_manager_complex.record_spend(user_id, 1.0)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: task(), range(iterations)))

    # All should succeed as limit is 100.0 and we spend 20.0
    assert all(results)

    date_str = sync_manager_complex.guard._get_date_str()
    key = f"spend:v1:user:{user_id}:{date_str}"
    usage = sync_manager_complex.ledger.get_usage(key)

    # Assert usage matches iterations * 1.0
    # Floating point might be slightly off, using approx if needed, but 1.0 should be fine.
    assert usage == float(iterations)
