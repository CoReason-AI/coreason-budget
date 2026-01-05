# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import math
from typing import Optional


def validate_check_availability_inputs(user_id: str) -> None:
    """Validate inputs for check_availability."""
    if not user_id or not user_id.strip():
        raise ValueError("user_id must be a non-empty string.")


def validate_record_spend_inputs(
    user_id: str, amount: float, project_id: Optional[str] = None, model: Optional[str] = None
) -> None:
    """Validate inputs for record_spend."""
    if not user_id or not user_id.strip():
        raise ValueError("user_id must be a non-empty string.")
    if not math.isfinite(amount):
        raise ValueError("Amount must be a finite number.")
    if project_id is not None and not project_id.strip():
        raise ValueError("project_id must be a non-empty string if provided.")
    if model is not None and not model.strip():
        raise ValueError("model must be a non-empty string if provided.")
