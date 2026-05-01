---
name: pdp-system-guide
description: Use this skill when developing, operating, or updating data in integrasi_data_skor_rekomendasi_desa to stay aligned with the official architecture, upload-process-commit SOP, and dev-to-main release flow. It also enforces strict Python, FastAPI development standards, and strict resource limitations.
---

# PDP System Guide

## When to use
Use this skill whenever work touches one of these areas:
- backend, frontend, or infrastructure changes in this project.
- troubleshooting empty data or query errors.
- writing type-safe Python with complete type coverage.
- building or modifying REST APIs with FastAPI.
- implementing async/await patterns for I/O operations.
- setting up pytest suites or implementing Pydantic V2 validation.
- optimizing performance for strict hardware limits (2 Cores, 4GB RAM, SSD).
- only focused on `dev` branch.

## Core principles
- `dev` is the active development branch (what you should be working on).
- `main` is the production branch.
- Data updates must follow the official API flow: upload -> process -> commit.
- Active databases are year-based: `desa_db/dbs/data_<year>.duckdb`.
- Do not commit `.env` or `.duckdb` without explicit data release approval.

## Resource & Architecture Constraints (2 Cores, 4GB RAM, SSD)
- **No in-memory caching:** Do not store large dictionaries, dataframes, or use memory-based cache decorators for endpoints. It will exhaust the 4GB RAM limit.
- **Disk-based pre-rendering:** Leverage the SSD. All heavy aggregations, public dashboards (e.g., IKU data), or complex `con.execute().pl()` transformations must be pre-rendered to static files in the `.cache/` directory during the data commit phase. Create `.cache/` if it does not exist.
- **Serve from disk:** Public endpoints must read and return these pre-rendered static files from `.cache/` rather than dynamically calculating data on the fly.
- **Static lists:** Data that rarely changes (e.g., Indonesian provinces) must not be queried from the backend database repeatedly. Serve them via a static JSON file or cache them directly on the frontend.
- **Config logic:** Store static if/else mapping logic or configuration rules in the `.config/` directory.
- **Recommendation logic:** Editing the logic behind helpers_get_public_iku_json is more preferable than creating new endpoints, unless something needed more logic to change (refactor, some part can be combined etc).

## Language policy
- Use English for implementation work, code-related explanations, and development instructions.
- Prefer terminology already established in this codebase when it improves consistency.

## Quick workflow
1. Confirm your working branch is `dev`.
2. Run the docker stack and make sure all services are `Up`.
3. Apply code changes or data updates.
4. Run minimum validation:
   - login/logout,
   - target-year query endpoints,
   - recommendation and IKU dashboards,
   - backend logs without `database does not exist`.
5. Apply minimum changes if possible on the `middleware.py` or `server.py`, example if it doesn't need more API then don't create API.
6. Prepare PR from `dev` only after the QA checklist passes.

## Data update SOP (short)
1. `POST /upload/init/{year}`
2. `POST /upload/chunk/{year}`
3. `POST /upload/finalize/{year}`
4. `POST /preview_excel/{year}`
5. `POST /analyze_header/{year}`
6. `POST /process_excel/{year}`
   *Trigger pre-rendering functions here to update `.cache/` files.*
7. Commit data through admin/backend flow, then verify query and dashboard outputs.

---

# Backend & API Development Standards

## Core Python & FastAPI Workflow
1. **Analyze requirements:** Identify endpoints, data models, auth needs, structure, and dependencies.
2. **Design interfaces & schemas:** Create Pydantic V2 models for validation, dataclasses, and protocols.
3. **Implement:** Write async endpoints with proper dependency injection and Pythonic code. Ensure full type hints and error handling.
4. **Secure:** Add authentication (JWT), authorization, rate limiting.
5. **Test:** Create comprehensive pytest suite (>90% coverage) with `pytest-asyncio` and `httpx`. Run tests after each endpoint group.
6. **Validate:** Run `black` and `ruff`. Verify OpenAPI docs at `/docs` reflects the intended API surface.
7. **Checkpoint:** If tests fail, debug assertions and iterate.

## Constraints

### MUST DO
- Type hints for all function signatures and class attributes (FastAPI requires them).
- PEP 8 compliance with `black` formatting.
- Comprehensive docstrings (Google style). Triple double quotes SHOULD EXIST on functions, explaining what it does and what it outputs for Args, Returns, Raises.
- Test coverage exceeding 90% with `pytest`.
- Use `X | None` instead of `Optional[X]` (Python 3.10+).
- Async/await for all I/O-bound operations.
- Dataclasses over manual init methods.
- Context managers for resource handling.
- Use Pydantic V2 syntax (`field_validator`, `model_validator`, `model_config`).
- Use `Annotated` pattern for dependency injection.
- Return proper HTTP status codes.
- Pre-render heavy calculations to `.cache/` and serve the static files for public endpoints.

### MUST NOT DO
- Execute heavy DuckDB/Polars aggregations dynamically on public-facing endpoints.
- Store cache variables in backend RAM.
- Query the database for static, non-growing lists.
- Skip type annotations on public APIs.
- Use mutable default arguments.
- Mix sync and async code improperly.
- Use synchronous database operations (unless strictly constrained by DuckDB connection patterns, which must then be isolated).
- Use bare `except` clauses.
- Hardcode secrets or configuration values.
- Use deprecated stdlib modules (use `pathlib` not `os.path`).
- Skip Pydantic validation.
- Store passwords in plain text or expose sensitive data in responses.
- Use Pydantic V1 syntax (`@validator`, `class Config`).

---

# Code Examples

## Type-annotated function with error handling
```python
from pathlib import Path

def read_config(path: Path) -> dict[str, str]:
    """Read configuration from a file.

    Args:
        path: Path to the configuration file.

    Returns:
        Parsed key-value configuration entries.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If a line cannot be parsed.
    """
    config: dict[str, str] = {}
    with path.open() as f:
        for line in f:
            key, _, value = line.partition("=")
            if not key.strip():
                raise ValueError(f"Invalid config line: {line!r}")
            config[key.strip()] = value.strip()
    return config
```

## Dataclass with validation

```python
from dataclasses import dataclass, field

@dataclass
class AppConfig:
    host: str
    port: int
    debug: bool = False
    allowed_origins: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (1 <= self.port <= 65535):
            raise ValueError(f"Invalid port: {self.port}")
```

## Async pattern

```python
import asyncio
import httpx

async def fetch_all(urls: list[str]) -> list[bytes]:
    """Fetch multiple URLs concurrently."""
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.content for r in responses]
```

## pytest fixture and parametrize

```python
import pytest
from pathlib import Path

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.txt"
    cfg.write_text("host=localhost\nport=8080\n")
    return cfg

@pytest.mark.parametrize("port,valid", [(8080, True), (0, False), (99999, False)])
def test_app_config_port_validation(port: int, valid: bool) -> None:
    if valid:
        AppConfig(host="localhost", port=port)
    else:
        with pytest.raises(ValueError):
            AppConfig(host="localhost", port=port)
```

## FastAPI Schema + Endpoint + Dependency Injection

**schemas.py**
```python
from pydantic import BaseModel, EmailStr, field_validator, model_config

class UserCreate(BaseModel):
    model_config = model_config(str_strip_whitespace=True)

    email: EmailStr
    password: str
    name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

class UserResponse(BaseModel):
    model_config = model_config(from_attributes=True)

    id: int
    email: EmailStr
    name: str | None = None
```

**routers/users.py**
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from app.database import get_db
from app.schemas import UserCreate, UserResponse
from app import crud

router = APIRouter(prefix="/users", tags=["users"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: DbDep) -> UserResponse:
    existing = await crud.get_user_by_email(db, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return await crud.create_user(db, payload)
```

**crud.py**
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User
from app.schemas import UserCreate
from app.security import hash_password

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    user = User(email=payload.email, hashed_password=hash_password(payload.password), name=payload.name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

## JWT Authentication Snippet

**security.py**
```python
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated

SECRET_KEY = "read-from-env"  # use os.environ / settings
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def create_access_token(subject: str, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    payload = {"sub": subject, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject: str | None = data.get("sub")
        if subject is None:
            raise ValueError
        return subject
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

CurrentUser = Annotated[str, Depends(get_current_user)]
```
