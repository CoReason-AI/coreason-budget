# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import os
from coreason_budget.config import CoreasonBudgetConfig


def test_config_defaults():
    """Test default configuration values."""
    config = CoreasonBudgetConfig()
    assert config.redis_url == "redis://localhost:6379"
    assert config.daily_user_limit_usd == 10.0
    assert config.daily_project_limit_usd == 500.0
    assert config.daily_global_limit_usd == 5000.0


def test_config_env_vars():
    """Test configuration override via environment variables."""
    os.environ["COREASON_BUDGET_REDIS_URL"] = "redis://custom:6379"
    os.environ["COREASON_BUDGET_DAILY_USER_LIMIT_USD"] = "50.0"

    try:
        config = CoreasonBudgetConfig()
        assert config.redis_url == "redis://custom:6379"
        assert config.daily_user_limit_usd == 50.0
        # Check that others remain default
        assert config.daily_project_limit_usd == 500.0
    finally:
        # Cleanup
        del os.environ["COREASON_BUDGET_REDIS_URL"]
        del os.environ["COREASON_BUDGET_DAILY_USER_LIMIT_USD"]
