from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis.exceptions import RedisError

from coreason_budget.config import BudgetConfig
from coreason_budget.exceptions import BudgetExceededError
from coreason_budget.manager import BudgetManager
from coreason_budget.utils.logger import logger


class CheckBudgetRequest(BaseModel):  # type: ignore[misc]
    user_id: str
    project_id: Optional[str] = None
    estimated_cost: float = 0.0


class RecordSpendRequest(BaseModel):  # type: ignore[misc]
    user_id: str
    cost: float
    project_id: Optional[str] = None
    model: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing BudgetManager...")
    config = BudgetConfig()
    budget_manager = BudgetManager(config)

    # Pre-connect (fail fast if redis is down on startup, though from_url is lazy)
    # The requirement says "Initialize ... once".
    # We can rely on health check or let it connect lazily.
    # However, BudgetManager._async_ledger uses redis-py which handles connection.

    app.state.budget = budget_manager
    yield
    logger.info("Closing BudgetManager...")
    await budget_manager.close()


app = FastAPI(lifespan=lifespan)


@app.post("/check")
async def check_budget(request: CheckBudgetRequest) -> Dict[str, str]:
    budget: BudgetManager = app.state.budget
    try:
        await budget.check_availability(
            user_id=request.user_id,
            project_id=request.project_id,
            estimated_cost=request.estimated_cost,
        )
        return {"status": "allowed"}
    except BudgetExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except ValueError as e:
        # Validation error from manager
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/spend")
async def record_spend(request: RecordSpendRequest) -> Dict[str, str]:
    budget: BudgetManager = app.state.budget
    try:
        await budget.record_spend(
            user_id=request.user_id,
            cost=request.cost,
            project_id=request.project_id,
            model=request.model,
        )
        return {"status": "recorded"}
    except ValueError as e:
        # Validation error from manager
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/health")
async def health_check() -> Dict[str, str]:
    budget: BudgetManager = app.state.budget
    try:
        # Accessing private member _async_ledger as per plan/requirements suggestion
        # Ideally we might want a public method, but we are inside the package.
        await budget._async_ledger._redis.ping()
        return {"status": "healthy", "redis": "connected"}
    except (RedisError, ConnectionError, Exception) as e:
        raise HTTPException(status_code=503, detail="Redis connection failed") from e
