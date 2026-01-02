# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# We need to reload the module to test the initialization logic
import sys
import importlib

def test_logger_dir_creation():
    """Test that logs directory is created if it doesn't exist."""
    # This is tricky because the module code runs on import.
    # We need to simulate the absence of the logs directory.

    # 1. Remove "logs" dir if exists (safe in sandbox?)
    log_path = Path("logs")
    if log_path.exists():
        shutil.rmtree(log_path)

    assert not log_path.exists()

    # 2. Force reload of logger module
    if "coreason_budget.utils.logger" in sys.modules:
        del sys.modules["coreason_budget.utils.logger"]

    import coreason_budget.utils.logger

    assert log_path.exists()
    assert log_path.is_dir()
