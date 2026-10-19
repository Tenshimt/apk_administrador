"""Shared fixtures for the test suite."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear rate-limiter state between tests to avoid 429s."""
    import dependencies.rate_limit as rl
    rl._buckets.clear()
    yield
    rl._buckets.clear()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def registered_store(client):
    """Create a test store and return login credentials."""
    payload = {
        "store_name": "Test Store",
        "store_slug": "test-store",
        "owner_email": "owner@test.com",
        "owner_password": "Test1234!",
        "owner_full_name": "Test Owner",
    }
    resp = await client.post("/auth/register-store", json=payload)
    assert resp.status_code == 201
    return payload


@pytest_asyncio.fixture
async def auth_headers(client, registered_store):
    """Return authorization headers for the test store owner."""
    resp = await client.post("/auth/login", json={
        "email": registered_store["owner_email"],
        "password": registered_store["owner_password"],
        "store_slug": registered_store["store_slug"],
    })
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
