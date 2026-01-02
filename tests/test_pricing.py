# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from unittest.mock import patch

import pytest

from coreason_budget.pricing import PricingEngine


def test_calculate_cost_success() -> None:
    """Test successful cost calculation."""
    engine = PricingEngine()

    with patch("litellm.completion_cost") as mock_cost:
        mock_cost.return_value = 0.03

        cost = engine.calculate("gpt-4", 100, 200)
        assert cost == 0.03
        mock_cost.assert_called_once_with(model="gpt-4", prompt_tokens=100, completion_tokens=200)


def test_calculate_cost_failure() -> None:
    """Test failure in cost calculation."""
    engine = PricingEngine()

    with patch("litellm.completion_cost") as mock_cost:
        mock_cost.side_effect = Exception("Model not found")

        with pytest.raises(Exception, match="Model not found"):
            engine.calculate("unknown-model", 10, 10)


def test_calculate_with_override() -> None:
    """Test cost calculation with configuration override."""
    # We need to mock the config structure since we haven't updated it yet,
    # but the test code needs to be valid python.
    # So we will import config classes after we define them?
    # Or just mock the config object to have the attribute.
    from unittest.mock import MagicMock

    from coreason_budget.config import CoreasonBudgetConfig

    # We can't use the real config yet because it doesn't have the field.
    # But we can pass a mock or a modified object if PricingEngine accepts it.
    # Current PricingEngine doesn't accept config. This test expects it to.

    # Mock the config
    mock_config = MagicMock(spec=CoreasonBudgetConfig)

    # Define a simple object for the price
    class MockPrice:
        input_cost_per_token = 0.0001
        output_cost_per_token = 0.0002

    mock_config.model_price_overrides = {"custom-gpt": MockPrice()}

    # This will fail because PricingEngine.__init__ doesn't take args
    engine = PricingEngine(config=mock_config)

    # 100 in * 0.0001 = 0.01
    # 100 out * 0.0002 = 0.02
    # Total = 0.03
    cost = engine.calculate("custom-gpt", 100, 100)

    # Use approx because of float math
    assert cost == pytest.approx(0.03)

    # Verify litellm was NOT called
    with patch("litellm.completion_cost") as mock_cost:
        engine.calculate("custom-gpt", 100, 100)
        mock_cost.assert_not_called()
