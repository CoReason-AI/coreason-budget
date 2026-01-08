# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

"""Coreason Budget Package.

This package provides financial guardrails and budget enforcement for LLM usage.
"""

from coreason_budget.config import CoreasonBudgetConfig
from coreason_budget.exceptions import BudgetExceededError, RedisConnectionError
from coreason_budget.manager import BudgetManager

# Alias for convenience/compatibility with intended usage
BudgetConfig = CoreasonBudgetConfig

__all__ = [
    "BudgetManager",
    "BudgetConfig",
    "CoreasonBudgetConfig",
    "BudgetExceededError",
    "RedisConnectionError",
]
