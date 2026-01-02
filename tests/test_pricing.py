# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import pytest
from unittest.mock import patch
from coreason_budget.pricing import PricingEngine

def test_calculate_cost_success():
    """Test successful cost calculation."""
    engine = PricingEngine()

    with patch("litellm.completion_cost") as mock_cost:
        mock_cost.return_value = 0.03

        cost = engine.calculate("gpt-4", 100, 200)
        assert cost == 0.03
        mock_cost.assert_called_once_with(
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=200
        )

def test_calculate_cost_failure():
    """Test failure in cost calculation."""
    engine = PricingEngine()

    with patch("litellm.completion_cost") as mock_cost:
        mock_cost.side_effect = Exception("Model not found")

        with pytest.raises(Exception, match="Model not found"):
            engine.calculate("unknown-model", 10, 10)
