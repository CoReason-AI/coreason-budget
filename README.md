# coreason-budget (The Controller)

**Mission:** Enforce Financial Operations (FinOps) guardrails for LLM usage.

This package acts as the "Controller," treating Compute (Tokens) as Cash. It enforces daily quotas and rejects requests immediately if limits are exceeded.

## Features

*   **Atomic Counting:** Uses Redis for high-speed, atomic, thread-safe counters.
*   **Hierarchical Quotas:** Enforces limits at User, Project, and Global scopes.
*   **Fail Closed:** Security-first design; if the budget cannot be checked, the transaction is blocked.
*   **Manual Integration:** Designed to be integrated into your middleware with a "Check-then-Charge" lifecycle.

## Installation

```bash
pip install coreason-budget
```

or with Poetry:

```bash
poetry add coreason-budget
```

## Usage

The package exposes a `BudgetManager` that you integrate into your API flow.

### 1. Configuration

The system is configured via `BudgetConfig` or environment variables (`COREASON_BUDGET_*`).

```python
from coreason_budget import BudgetManager, BudgetConfig, BudgetExceededError

# Initialize with Redis URL and Limits
config = BudgetConfig(
    redis_url="redis://localhost:6379",
    daily_user_limit_usd=10.0,
    daily_project_limit_usd=500.0,
    daily_global_limit_usd=5000.0
)
budget = BudgetManager(config)
```

### 2. The Check-Charge Lifecycle

The middleware operates in two phases: **Pre-Flight Check** and **Post-Flight Charge**.

```python
# --- Phase 1: Pre-Flight Check ---
# Before calling the LLM, verify budget availability.
user_id = "user_123"
try:
    # Check if user can spend (optionally pass estimated_cost)
    await budget.check_availability(user_id)
except BudgetExceededError:
    # Block the request immediately
    return Response("Daily Limit Reached", status_code=429)

# --- Execute LLM ---
# Perform the inference call
response = await llm.generate(...)

# --- Phase 2: Post-Flight Charge ---
# Calculate precise cost based on provider metadata
cost = budget.pricing.calculate(
    model="gpt-4",
    input_tokens=response.usage.prompt_tokens,
    output_tokens=response.usage.completion_tokens
)

# Atomically record the spend
await budget.record_spend(
    user_id=user_id,
    cost=cost,
    project_id="project_launch_sim", # Optional
    model="gpt-4"                    # Optional, for logging
)
print(f"Transaction Cost: ${cost}")
```

## Configuration Options

| Environment Variable | Description | Default |
| -------------------- | ----------- | ------- |
| `COREASON_BUDGET_REDIS_URL` | Redis Connection URL | *Required* |
| `COREASON_BUDGET_DAILY_USER_LIMIT_USD` | Daily limit per user ($) | `10.0` |
| `COREASON_BUDGET_DAILY_PROJECT_LIMIT_USD` | Daily limit per project ($) | `500.0` |
| `COREASON_BUDGET_DAILY_GLOBAL_LIMIT_USD` | Global hard limit ($) | `5000.0` |
| `COREASON_BUDGET_LOG_PATH` | Path to log file | `logs/app.log` |

## Architecture

*   **RedisLedger:** Manages atomic increments and key expiration (UTC Midnight).
*   **BudgetGuard:** Enforces limits and raises `BudgetExceededError`.
*   **PricingEngine:** Calculates costs using `liteLLM` or configured overrides.

## Development

1.  **Install Dependencies:**
    ```bash
    poetry install
    ```

2.  **Run Tests:**
    ```bash
    poetry run pytest
    ```

3.  **Code Quality:**
    ```bash
    poetry run pre-commit run --all-files
    ```
