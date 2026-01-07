import os
from unittest.mock import patch

import pytest


def test_logger_path_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    # We need to reload the module to test side effects of import
    # But reloading loguru logger setup is tricky because it's global state.
    # However, we can just verify the logic by importing it in a subprocess or
    # just trusting the code since it's simple.
    # But requirement says "Add a test case".
    # Since the module code runs on import, we can't easily test it in the same process
    # if it's already imported.
    # We can use `importlib.reload` but `logger.add` adds handlers cumulatively.
    # We should probably mock `logger.add` and `os.makedirs`.

    with (
        patch.dict(os.environ, {"COREASON_BUDGET_LOG_PATH": "custom/logs/test.log"}),
        patch("coreason_budget.utils.logger.logger.add") as mock_add,
        patch("os.makedirs") as mock_makedirs,
        patch("sys.stderr"),
    ):
        # We need to reload the module
        import importlib

        import coreason_budget.utils.logger

        importlib.reload(coreason_budget.utils.logger)

        # Verify makedirs called with custom path dir
        mock_makedirs.assert_called_with("custom/logs", exist_ok=True)

        # Verify logger.add called with custom path
        # Note: logger.add is called twice (console and file)
        # Check calls
        calls = mock_add.call_args_list
        # Found file handler call
        file_call = next((call for call in calls if "custom/logs/test.log" in str(call)), None)
        assert file_call is not None
