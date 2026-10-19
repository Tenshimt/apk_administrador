"""Second-review regression tests (bugs 1, 3b, 4, 5, 6, 7, 8, 9)."""
import os
import tempfile
import pytest
from decimal import Decimal


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _product(client, headers, sku, unit="unit", stock=20, price=5000):
    resp = await client.post("/products", json={
        "sku": sku, "name": f"Prod {sku}", "price_cents": price,
        "cost_cents": 2000, "stock_quantity": stock, "low_stock_threshold": 2,
        "unit": unit,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _box_product(client, headers, sku, m2_per_box="1.44", stock=20, price=5000):
    resp = await client.post("/products", json={
        "sku": sku, "name": f"Box {sku}", "price_cents": price,
        "cost_cents": 2000, "stock_quantity": stock, "low_stock_threshold": 2,
        "unit": "box", "m2_per_box": m2_per_box,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _client_create(client, headers, name, credit_limit=None):
    resp = await client.post("/clients", json={
        "full_name": name, "credit_limit_cents": credit_limit,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _viewer_headers(client, auth_headers):
    await client.post("/users", json={
        "email": "viewer2@test.com", "password": "Test1234!",
        "full_name": "Viewer", "role": "viewer",
    }, headers=auth_headers)
    resp = await client.post("/auth/login", json={
        "email": "viewer2@test.com", "password": "Test1234!", "store_slug": "test-store",
    })
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ─── Bug 1: alembic.ini path ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alembic_ini_at_project_root():
    """alembic.ini must live at ceramica-backend/alembic.ini, not alembic/alembic.ini."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.isfile(os.path.join(base, "alembic.ini")), \
        "alembic.ini not found at project root"
    assert not os.path.isfile(os.path.join(base, "alembic", "alembic.ini")), \
        "alembic.ini should be moved out of alembic/ subdirectory"


@pytest.mark.asyncio
async def test_alembic_upgrade_on_temp_db():
    """Alembic upgrade head must work on a fresh temp SQLite DB."""
    import asyncio
    from alembic import command
    from alembic.config import Config as AlembicConfig

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        cfg = AlembicConfig(os.path.join(base, "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, command.upgrade, cfg, "head")
    finally:
        os.unlink(db_path)


# ─── Bug 3b: FIFO payment debt invariant ──────────────────────────────────────

@pytest.mark.asyncio
async def test_debt_invariant_after_sales_payments_cancel(client, auth_headers):
    """client.debt_cents must always equal sum of balance_cents of pending/partial sales."""
    p1 = await _product(client, auth_headers, "DEBT-INV-P1", stock=10, price=3000)
    p2 = await _product(client, auth_headers, "DEBT-INV-P2", stock=10, price=4000)
    cli = await _client_create(client, auth_headers, "Debt Invariant Client", credit_limit=None)

    sale1 = (await client.post("/sales", json={
        "items": [{"product_id": p1["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0, "client_id": cli["id"],
    }, headers=auth_headers)).json()["data"]
    sale2 = (await client.post("/sales", json={
        "items": [{"product_id": p2["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0, "client_id": cli["id"],
    }, headers=auth_headers)).json()["data"]

    # Pay 2000 FIFO
    pay = await client.post(f"/clients/{cli['id']}/payment", json={
        "amount_cents": 2000, "method": "cash",
    }, headers=auth_headers)
    assert pay.status_code == 200

    # Cancel sale2 (no payments on it, balance still 4000)
    cancel = await client.post(f"/sales/{sale2['id']}/cancel", headers=auth_headers)
    assert cancel.status_code == 200

    # Check debt == sum of remaining unpaid balances
    debt = (await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)).json()["data"]
    s1 = (await client.get(f"/sales/{sale1['id']}", headers=auth_headers)).json()["data"]
    # sale1 has 1000 paid, balance 2000; sale2 cancelled
    expected_debt = s1["balance_cents"]
    assert debt["debt_cents"] == expected_debt, \
        f"debt={debt['debt_cents']} but sum of balances={expected_debt}"


@pytest.mark.asyncio
async def test_fifo_payment_exceeds_actual_balances_rejected(client, auth_headers):
    """Payment must be rejected if it exceeds sum of unpaid sale balances (not client.debt_cents)."""
    p = await _product(client, auth_headers, "FIFO-BAL-P1", stock=5, price=5000)
    cli = await _client_create(client, auth_headers, "Balance Check Client", credit_limit=None)

    await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0, "client_id": cli["id"],
    }, headers=auth_headers)

    # Payment exceeds actual sale balance
    resp = await client.post(f"/clients/{cli['id']}/payment", json={
        "amount_cents": 99999, "method": "cash",
    }, headers=auth_headers)
    assert resp.status_code == 400


# ─── Bug 4: Viewer read-only ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_viewer_cannot_create_sale(client, auth_headers):
    viewer_h = await _viewer_headers(client, auth_headers)
    p = await _product(client, auth_headers, "VIEW-SALE-P1")
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0, "payment_method": "cash", "payment_amount_cents": 5000,
    }, headers=viewer_h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_client(client, auth_headers):
    viewer_h = await _viewer_headers(client, auth_headers)
    resp = await client.post("/clients", json={"full_name": "Should Fail"}, headers=viewer_h)
    assert resp.status_code == 403


# ─── Bug 5: Negative payment_amount_cents ─────────────────────────────────────

@pytest.mark.asyncio
async def test_negative_payment_amount_returns_422(client, auth_headers):
    p = await _product(client, auth_headers, "NEG-PAY-P1")
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": -500,
    }, headers=auth_headers)
    assert resp.status_code == 422


# ─── Bug 6: Fractional boxes/units rejected ───────────────────────────────────

@pytest.mark.asyncio
async def test_fractional_box_quantity_rejected(client, auth_headers):
    p = await _box_product(client, auth_headers, "FRAC-BOX-001")
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": "2.7", "discount_cents": 0}],
        "discount_cents": 0, "payment_method": "cash", "payment_amount_cents": 13500,
    }, headers=auth_headers)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_fractional_unit_quantity_rejected(client, auth_headers):
    p = await _product(client, auth_headers, "FRAC-UNIT-001", unit="unit")
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": "1.5", "discount_cents": 0}],
        "discount_cents": 0, "payment_method": "cash", "payment_amount_cents": 7500,
    }, headers=auth_headers)
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_fractional_m2_quantity_allowed(client, auth_headers):
    p = await _product(client, auth_headers, "FRAC-M2-001", unit="m2", stock=20, price=3000)
    total = int(round(Decimal("2.5") * 3000))
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": "2.5", "discount_cents": 0}],
        "discount_cents": 0, "payment_method": "cash", "payment_amount_cents": total,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text


# ─── Bug 7: PO quantities Decimal ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_po_fractional_quantity_ordered(client, auth_headers):
    sup = (await client.post("/suppliers", json={"name": "PO Supplier"}, headers=auth_headers)).json()["data"]
    p = await _product(client, auth_headers, "PO-DEC-001", stock=50)
    resp = await client.post("/suppliers/purchase-orders", json={
        "supplier_id": sup["id"],
        "items": [{"product_id": p["id"], "quantity_ordered": "12.5", "unit_cost_cents": 2000}],
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    po = resp.json()["data"]
    item = po["items"][0]
    assert Decimal(str(item["quantity_ordered"])) == Decimal("12.5")


# ─── Bug 8: Rate limiter counts only failed attempts ──────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_counts_only_failures(client, registered_store):
    """5 failed attempts → 6th is 429; a success resets the counter."""
    # 5 bad password attempts
    for _ in range(5):
        await client.post("/auth/login", json={
            "email": registered_store["owner_email"],
            "password": "wrong-password",
            "store_slug": registered_store["store_slug"],
        })
    # 6th attempt with wrong password → 429
    resp = await client.post("/auth/login", json={
        "email": registered_store["owner_email"],
        "password": "wrong-password",
        "store_slug": registered_store["store_slug"],
    })
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_successful_login_resets_counter(client, registered_store):
    """A successful login resets the failure counter."""
    # 4 bad attempts (under limit)
    for _ in range(4):
        await client.post("/auth/login", json={
            "email": registered_store["owner_email"],
            "password": "wrong-password",
            "store_slug": registered_store["store_slug"],
        })
    # successful login resets
    good = await client.post("/auth/login", json={
        "email": registered_store["owner_email"],
        "password": registered_store["owner_password"],
        "store_slug": registered_store["store_slug"],
    })
    assert good.status_code == 200
    # After reset, should be able to fail again without hitting 429
    resp = await client.post("/auth/login", json={
        "email": registered_store["owner_email"],
        "password": "wrong-password",
        "store_slug": registered_store["store_slug"],
    })
    assert resp.status_code == 401  # not 429


# ─── Bug 9: credit_limit_cents nullable ───────────────────────────────────────

@pytest.mark.asyncio
async def test_credit_limit_zero_blocks_credit_sale(client, auth_headers):
    """credit_limit_cents=0 means NO credit allowed."""
    p = await _product(client, auth_headers, "CL0-P1", stock=5, price=3000)
    cli = await _client_create(client, auth_headers, "No Credit Client", credit_limit=0)
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0, "client_id": cli["id"],
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_credit_limit_null_means_unlimited(client, auth_headers):
    """credit_limit_cents=None means unlimited credit."""
    p = await _product(client, auth_headers, "CLNULL-P1", stock=5, price=50000)
    cli = await _client_create(client, auth_headers, "Unlimited Credit Client", credit_limit=None)
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0, "client_id": cli["id"],
    }, headers=auth_headers)
    assert resp.status_code == 201
