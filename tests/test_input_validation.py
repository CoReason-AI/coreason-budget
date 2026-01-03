import pytest

from coreason_budget import BudgetExceededError, BudgetManager


@pytest.mark.asyncio
async def test_empty_strings(manager: BudgetManager) -> None:
    """Test that empty strings are rejected."""
    user_id = ""
    project_id = ""
    model = ""

    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        await manager.record_spend(user_id, 1.0, project_id="p", model="m")

    with pytest.raises(ValueError, match="project_id must be a non-empty string"):
        await manager.record_spend("u", 1.0, project_id=project_id, model="m")

    with pytest.raises(ValueError, match="model must be a non-empty string"):
        await manager.record_spend("u", 1.0, project_id="p", model=model)

    with pytest.raises(ValueError, match="user_id must be a non-empty string"):
        await manager.check_availability(user_id)


@pytest.mark.asyncio
async def test_special_characters_in_ids(manager: BudgetManager) -> None:
    """Test IDs with colons, spaces, and other special chars."""
    user_id = "user:123"
    project_id = "proj/subproj"
    model = "gpt-4 (preview)"

    # Key should be "spend:v1:user:user:123:..."
    await manager.record_spend(user_id, 1.0, project_id=project_id, model=model)

    # Should be able to read back
    # We can inspect the internal ledger to verify keys if we want, but functional test is better.
    # If we spend limit, it should block.

    limit = manager.config.daily_user_limit_usd
    await manager.record_spend(user_id, limit, project_id=project_id, model=model)

    with pytest.raises(BudgetExceededError):
        await manager.check_availability(user_id, project_id=project_id)


@pytest.mark.asyncio
async def test_nan_infinity_amount(manager: BudgetManager) -> None:
    """Test passing NaN or Infinity as amount."""
    user_id = "user_nan"
    project_id = "p"
    model = "m"

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        await manager.record_spend(user_id, float("nan"), project_id=project_id, model=model)

    with pytest.raises(ValueError, match="Amount must be a finite number"):
        await manager.record_spend(user_id, float("inf"), project_id=project_id, model=model)


@pytest.mark.asyncio
async def test_unicode_ids(manager: BudgetManager) -> None:
    """Test Unicode characters in IDs."""
    user_id = "user_👍"
    project_id = "proj_🚀"
    model = "m_€"

    await manager.record_spend(user_id, 1.0, project_id=project_id, model=model)
    await manager.check_availability(user_id)
