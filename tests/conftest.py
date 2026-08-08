"""
Test Configuration and Fixtures
Provides isolated test database, mock settings, and FastAPI TestClient.
"""

import os
import pytest
import asyncio
from typing import AsyncGenerator
from unittest.mock import patch, MagicMock

# Set test environment BEFORE any backend imports
os.environ["USE_MOCK_DATA"] = "true"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"

# Monkey-patch the database module to avoid PostgreSQL-specific kwargs
import backend.database as _db_module

_original_create_engine = _db_module.create_async_engine.__func__ if hasattr(_db_module.create_async_engine, '__func__') else None

def _patched_create_engine(url, **kwargs):
    """Remove PostgreSQL-specific kwargs for SQLite."""
    if "sqlite" in str(url).lower():
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_pre_ping", None)
    return _db_module.create_async_engine.__wrapped__(url, **kwargs) if hasattr(_db_module.create_async_engine, '__wrapped__') else _db_module.create_async_engine.__wrapped__(url, **kwargs)

# Replace the engine creation in database module
import sqlalchemy.ext.asyncio as _sa_asyncio
_original_engine_func = _sa_asyncio.create_async_engine

def _safe_create_async_engine(url, **kwargs):
    """Create engine without PostgreSQL-specific kwargs for SQLite."""
    if "sqlite" in str(url).lower():
        kwargs.pop("pool_size", None)
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_pre_ping", None)
    return _original_engine_func(url, **kwargs)

_sa_asyncio.create_async_engine = _safe_create_async_engine

# Now import the rest - database module will use patched engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.database import Base, get_db, engine
from backend.main import app
from httpx import AsyncClient, ASGITransport


# --- Database Fixtures ---

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create in-memory SQLite async engine for tests."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with overridden database dependency."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# --- Mock Fixtures ---

@pytest.fixture
def mock_settings():
    """Provide mock settings for isolated tests."""
    return {
        "groq_api_key": "test_key",
        "groq_model": "llama-3.3-70b-versatile",
        "use_mock_data": True,
        "default_epsilon": 1.0,
        "max_privacy_budget": 10.0,
        "gradient_clip_norm": 1.0,
    }
