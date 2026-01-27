# Requirements

## Core Dependencies
These are required for the library to function.

*   `python`: >= 3.12
*   `redis`: ^7.1.0 (Redis client)
*   `litellm`: ^1.80.11 (Cost calculation)
*   `pydantic`: >= 2.0 (Data validation)
*   `pydantic-settings`: ^2.12.0 (Configuration management)
*   `loguru`: ^0.7.2 (Structured logging)

## Server Dependencies (Optional)
These are required only if running in **Server Mode** (Microservice).

*   `fastapi`: (Web framework)
*   `uvicorn`: (ASGI server)

## Development Dependencies
These are required for testing and development.

*   `pytest`
*   `pytest-asyncio`
*   `pytest-cov`
*   `ruff`
*   `pre-commit`
*   `fakeredis`
*   `httpx` (API testing)
*   `mkdocs`
*   `mkdocs-material`
