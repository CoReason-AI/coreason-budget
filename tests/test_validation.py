import pytest
from coreason_budget.validation import validate_check_availability_inputs, validate_record_spend_inputs

def test_validate_check_availability_inputs() -> None:
    validate_check_availability_inputs("user1")

    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        validate_check_availability_inputs("")

    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        validate_check_availability_inputs(None) # type: ignore

def test_validate_record_spend_inputs() -> None:
    validate_record_spend_inputs("user1", 10.0)
    validate_record_spend_inputs("user1", 10.0, "proj1", "model1")

    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        validate_record_spend_inputs("", 10.0)

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        validate_record_spend_inputs("user1", float('inf'))

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        validate_record_spend_inputs("user1", float('nan'))

    with pytest.raises(ValueError, match="project_id must be a non-empty string"):
        validate_record_spend_inputs("user1", 10.0, "")

    with pytest.raises(ValueError, match="model must be a non-empty string"):
        validate_record_spend_inputs("user1", 10.0, "proj1", "")
