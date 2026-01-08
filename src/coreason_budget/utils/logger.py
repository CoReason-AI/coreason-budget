import os
import sys

from loguru import logger

# Configure logger
# Remove default handler
logger.remove()

# Add console handler
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

# Add file handler
# Ensure logs directory exists
log_path = os.getenv("COREASON_BUDGET_LOG_PATH", "logs/app.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logger.add(
    log_path,
    rotation="500 MB",
    retention="10 days",
    level=os.getenv("LOG_LEVEL", "INFO"),
    serialize=True,  # JSON format
)

# Export logger
__all__ = ["logger"]
