# Usage

`coreason-budget` supports two primary modes of operation.

## 1. Library Mode (Python Integration)

Use this mode when you want to embed the budget controller directly into your Python application (e.g., inside an existing backend service).

### Configuration

```python
from coreason_budget import BudgetManager, BudgetConfig

config = BudgetConfig(
    redis_url="redis://localhost:6379",
    daily_user_limit_usd=10.0
)
manager = BudgetManager(config)
```

### Checking Budget

```python
from coreason_budget import BudgetExceededError

user_id = "user_123"

try:
    await manager.check_availability(user_id, estimated_cost=0.01)
    print("Budget available. Proceeding...")
except BudgetExceededError as e:
    print(f"Blocked: {e}")
```

### Recording Spend

```python
await manager.record_spend(
    user_id="user_123",
    cost=0.005,
    project_id="project_alpha",
    model="gpt-4"
)
```

---

## 2. Server Mode (Microservice)

Use this mode to deploy `coreason-budget` as a centralized service that multiple agents can query over HTTP.

### Running the Server

**Using Docker:**
```bash
docker run -p 8000:8000 -e COREASON_BUDGET_REDIS_URL="redis://..." coreason-budget
```

**Using Uvicorn directly:**
```bash
uvicorn coreason_budget.server:app --host 0.0.0.0 --port 8000
```

### API Examples

**Check Budget:**
```bash
curl -X POST http://localhost:8000/check \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123", "estimated_cost": 0.01}'
```

**Record Spend:**
```bash
curl -X POST http://localhost:8000/spend \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123", "cost": 0.01, "model": "gpt-4"}'
```
