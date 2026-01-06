# Coreason Budget

**The Controller.** This package enforces financial discipline. It treats Compute (Tokens) as Cash.

## Overview

`coreason-budget` is a Python package designed to enforce Financial Operations (FinOps) guardrails for LLM applications. It provides real-time budget tracking and rate limiting using Redis atomic counters.

### Key Features

*   **Real-time Budget Tracking:** Tracks token usage per user, project, and globally.
*   **Hierarchical Quotas:** Enforces limits at User ($10/day), Project ($500/day), and Global ($5000/day) scopes.
*   **Atomic Operations:** Uses Redis Lua scripts to ensure race-condition-free counting.
*   **Fail-Closed Security:** Rejects requests if budget checks fail, ensuring no unapproved spend.
*   **LiteLLM Integration:** Proxies cost calculations through LiteLLM for accurate pricing.

## Installation

```bash
pip install coreason-budget
```

Or using Poetry:

```bash
poetry add coreason-budget
```

## Configuration

Configuration is managed via `pydantic-settings`. You can set environment variables or pass a `BudgetConfig` object.

| Environment Variable | Default | Description |
| -------------------- | ------- | ----------- |
| `COREASON_BUDGET_REDIS_URL` | `redis://localhost:6379` | Connection string for Redis. |
| `COREASON_BUDGET_DAILY_USER_LIMIT_USD` | `10.0` | Daily spend limit per user. |
| `COREASON_BUDGET_DAILY_PROJECT_LIMIT_USD` | `500.0` | Daily spend limit per project. |
| `COREASON_BUDGET_DAILY_GLOBAL_LIMIT_USD` | `5000.0` | Hard global daily limit. |

## Usage

### Asynchronous (Recommended)

```python
from coreason_budget import BudgetManager, BudgetConfig, BudgetExceededError

# 1. Initialize
config = BudgetConfig(
    redis_url="redis://localhost:6379",
    daily_limit_usd=50.0  # Overrides default user limit
)
budget = BudgetManager(config)

async def handle_request(user_id: str, prompt: str):
    # 2. Pre-Flight Check (Fast)
    try:
        # Check if user has budget available
        await budget.check_availability(user_id)
    except BudgetExceededError:
        # Halt execution immediately
        return {"error": "Daily Limit Reached", "status": 429}

    # ... Run LLM ...
    # response = await llm.generate(prompt)

    # 3. Post-Flight Charge
    # Calculate precise cost based on provider metadata
    cost = budget.pricing.calculate(
        model="gpt-4",
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens
    )

    # Atomic increment
    await budget.record_spend(user_id, cost, project_id="proj_A", model="gpt-4")

    return response
```

### Synchronous

```python
from coreason_budget import SyncBudgetManager, BudgetConfig

budget = SyncBudgetManager(BudgetConfig())

try:
    budget.check_availability("user_123")
except BudgetExceededError:
    raise

# ...
```
