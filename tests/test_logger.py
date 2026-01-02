# Copyright (c) 2025 CoReason, Inc.
#
# This software is proprietary and dual-licensed.
# Licensed under the Prosperity Public License 3.0 (the "License").
# A copy of the license is available at https://prosperitylicense.com/versions/3.0.0
# For details, see the LICENSE file.
# Commercial use beyond a 30-day trial requires a separate license.
#
# Source Code: https://github.com/CoReason-AI/coreason_budget

from pathlib import Path
from coreason_budget.utils.logger import logger

def test_logger_setup():
    """Test that the logger is configured correctly."""
    assert logger is not None
    # Verify that the log file is created
    log_path = Path("logs/app.log")
    # We might need to log something to ensure the file is created if it's lazy
    logger.info("Test log entry")
    assert log_path.exists()
