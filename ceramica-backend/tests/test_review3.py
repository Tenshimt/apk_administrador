"""Third-review regression tests (role guards, alembic %(here)s, Redis shutdown)."""
import os
import asyncio
import tempfile
import pytest
from unittest.mock import AsyncMock


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _make_product(client, headers, sku, unit="unit", stock=10):
    resp = await client.post("/products", json={
        "sku": sku, "name": f"P {sku}", "price_cents": 5000,
        "cost_cents": 2000, "stock_quantity": stock,
        "low_stock_threshold": 2, "unit": unit,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _viewer_headers(client, auth_headers):
    await client.post("/users", json={
        "email": "viewer_r3@test.com", "password": "Test1234!",
        "full_name": "Viewer R3", "role": "viewer",
    }, headers=auth_headers)
    resp = await client.post("/auth/login", json={
        "email": "viewer_r3@test.com", "password": "Test1234!", "store_slug": "test-store",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _cashier_headers(client, auth_headers):
    await client.post("/users", json={
        "email": "cashier_r3@test.com", "password": "Test1234!",
        "full_name": "Cashier R3", "role": "cashier",
    }, headers=auth_headers)
    resp = await client.post("/auth/login", json={
        "email": "cashier_r3@test.com", "password": "Test1234!", "store_slug": "test-store",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


# ─── Bug 1: role guards on adjust-stock and expense ──────────────────────────

@pytest.mark.asyncio
async def test_viewer_cannot_adjust_stock(client, auth_headers):
    product = await _make_product(client, auth_headers, "ADJ-VIEW-01")
    viewer = await _viewer_headers(client, auth_headers)
    resp = await client.post(
        f"/products/{product['id']}/adjust-stock",
        json={"quantity_delta": -1, "reason": "adjustment"},
        headers=viewer,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_cashier_cannot_adjust_stock(client, auth_headers):
    product = await _make_product(client, auth_headers, "ADJ-CASH-01")
    cashier = await _cashier_headers(client, auth_headers)
    resp = await client.post(
        f"/products/{product['id']}/adjust-stock",
        json={"quantity_delta": -1, "reason": "adjustment"},
        headers=cashier,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_viewer_cannot_create_expense(client, auth_headers):
    viewer = await _viewer_headers(client, auth_headers)
    resp = await client.post("/finance/expense", json={
        "description": "Test expense", "amount_cents": 1000, "category": "other",
    }, headers=viewer)
    assert resp.status_code == 403, resp.text


FAKE_ID = "00000000-0000-0000-0000-000000000001"

WRITE_ENDPOINTS = [
    ("POST",   "/products",                                              {"sku": "X", "name": "X", "price_cents": 100, "cost_cents": 50, "stock_quantity": 1, "low_stock_threshold": 1}),
    ("PUT",    f"/products/{FAKE_ID}",                                   {"name": "X"}),
    ("DELETE", f"/products/{FAKE_ID}",                                   None),
    ("POST",   f"/products/{FAKE_ID}/adjust-stock",                      {"quantity_delta": -1, "reason": "adjustment"}),
    ("POST",   "/sales",                                                 {"items": [], "discount_cents": 0}),
    ("POST",   f"/sales/{FAKE_ID}/payment",                              {"amount_cents": 100, "method": "cash"}),
    ("POST",   f"/sales/{FAKE_ID}/cancel",                               None),
    ("POST",   "/clients",                                               {"full_name": "X"}),
    ("PUT",    f"/clients/{FAKE_ID}",                                    {"full_name": "Y"}),
    ("POST",   f"/clients/{FAKE_ID}/payment",                            {"amount_cents": 100, "method": "cash"}),
    ("POST",   "/suppliers",                                             {"name": "S"}),
    ("POST",   "/suppliers/purchase-orders",                             {"supplier_id": FAKE_ID, "items": []}),
    ("PATCH",  f"/suppliers/purchase-orders/{FAKE_ID}/receive",          {"items": []}),
    ("POST",   f"/suppliers/purchase-orders/{FAKE_ID}/payment",          {"amount_cents": 100}),
    ("POST",   "/finance/expense",                                       {"description": "X", "amount_cents": 100, "category": "other"}),
    ("POST",   "/users",                                                 {"email": "x@x.com", "password": "P1234!", "full_name": "X", "role": "cashier"}),
    ("PATCH",  f"/users/{FAKE_ID}",                                      {"full_name": "Y"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", WRITE_ENDPOINTS)
async def test_viewer_forbidden_on_write_endpoint(client, auth_headers, method, path, body):
    viewer = await _viewer_headers(client, auth_headers)
    fn = getattr(client, method.lower())
    kwargs = {"headers": viewer}
    if body is not None:
        kwargs["json"] = body
    resp = await fn(path, **kwargs)
    assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}: {resp.text}"


# ─── Bug 2: alembic.ini %(here)s ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alembic_migrations_from_different_cwd():
    """Alembic upgrade head must succeed when cwd != project directory."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    ini_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic.ini",
    )
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        try:
            os.chdir("/tmp")
            cfg = AlembicConfig(ini_path)
            cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

            def _run():
                command.upgrade(cfg, "head")

            await asyncio.get_event_loop().run_in_executor(None, _run)
        finally:
            os.chdir(original_cwd)
    # If no exception, migration succeeded from a different cwd


# ─── Bug 3: Redis shutdown resilience ────────────────────────────────────────

@pytest.mark.asyncio
async def test_connection_manager_shutdown_resilient_to_redis_error():
    """shutdown() must not raise even if Redis unsubscribe/close fails."""
    from websocket_manager import ConnectionManager

    mgr = ConnectionManager()
    pubsub_mock = AsyncMock()
    pubsub_mock.unsubscribe.side_effect = ConnectionError("Redis gone")
    redis_mock = AsyncMock()
    redis_mock.aclose.side_effect = ConnectionError("Redis gone")

    mgr._pubsub = pubsub_mock
    mgr._redis = redis_mock

    # Must not raise
    await mgr.shutdown()

    pubsub_mock.unsubscribe.assert_called_once()
    redis_mock.aclose.assert_called_once()
