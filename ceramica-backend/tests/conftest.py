"""Shared fixtures for the test suite."""

import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base, get_db
from main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with _SessionLocal() as session:
        yield session


async def _override_db():
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def client(db_session):
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
