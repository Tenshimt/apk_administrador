"""Phase 3 regression tests."""
import pytest


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _register_and_login(client, email, slug):
    await client.post("/auth/register-store", json={
        "store_name": f"Store {slug}", "store_slug": slug,
        "owner_email": email, "owner_password": "Test1234!",
        "owner_full_name": "Owner",
    })
    resp = await client.post("/auth/login", json={
        "email": email, "password": "Test1234!", "store_slug": slug,
    })
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _product(client, headers, sku, price=5000, cost=2000, wholesale=None, stock=20):
    body = {
        "sku": sku, "name": f"Product {sku}", "price_cents": price,
        "cost_cents": cost, "stock_quantity": stock, "low_stock_threshold": 5,
    }
    if wholesale:
        body["wholesale_price_cents"] = wholesale
    resp = await client.post("/products", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _client(client, headers, name, client_type="retail", credit_limit=None):
    resp = await client.post("/clients", json={
        "full_name": name, "client_type": client_type,
        "credit_limit_cents": credit_limit,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ─── 1. Roles ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cashier_cannot_create_product(client, auth_headers):
    """Cashier should be blocked from POST /products (owner/admin only)."""
    # Create a cashier
    owner_h = auth_headers
    resp = await client.post("/users", json={
        "email": "cashier@test.com", "password": "Test1234!",
        "full_name": "Cashier", "role": "cashier",
    }, headers=owner_h)
    assert resp.status_code == 201

    # Login as cashier
    login_resp = await client.post("/auth/login", json={
        "email": "cashier@test.com", "password": "Test1234!", "store_slug": "test-store",
    })
    cashier_token = login_resp.json()["data"]["access_token"]
    cashier_h = {"Authorization": f"Bearer {cashier_token}"}

    # Cashier cannot create product
    resp = await client.post("/products", json={
        "sku": "ROLE-P1", "name": "P", "price_cents": 1000,
        "cost_cents": 500, "stock_quantity": 10, "low_stock_threshold": 2,
    }, headers=cashier_h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_create_user(client, auth_headers):
    """Owner can create users via POST /users."""
    resp = await client.post("/users", json={
        "email": "newuser@test.com", "password": "Test1234!",
        "full_name": "New User", "role": "cashier",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["role"] == "cashier"
    assert data["email"] == "newuser@test.com"


@pytest.mark.asyncio
async def test_viewer_cannot_access_debt_aging(client, auth_headers):
    """Viewer should be blocked from GET /clients/debt-aging."""
    # Create viewer
    await client.post("/users", json={
        "email": "viewer@test.com", "password": "Test1234!",
        "full_name": "Viewer", "role": "viewer",
    }, headers=auth_headers)
    login_resp = await client.post("/auth/login", json={
        "email": "viewer@test.com", "password": "Test1234!", "store_slug": "test-store",
    })
    viewer_h = {"Authorization": f"Bearer {login_resp.json()['data']['access_token']}"}

    resp = await client.get("/clients/debt-aging", headers=viewer_h)
    assert resp.status_code == 403


# ─── 2. Rate limiting ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_login(client):
    """Exceed auth_rate_limit_requests → 429."""
    # settings default: 5 requests / 60s
    for _ in range(5):
        await client.post("/auth/login", json={
            "email": "x@x.com", "password": "bad", "store_slug": "no-store",
        })
    resp = await client.post("/auth/login", json={
        "email": "x@x.com", "password": "bad", "store_slug": "no-store",
    })
    assert resp.status_code == 429


# ─── 5. Consistent error format ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_404_uses_envelope(client, auth_headers):
    resp = await client.get("/products/nonexistent-id", headers=auth_headers)
    body = resp.json()
    assert "data" in body
    assert "error" in body
    assert "meta" in body
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validation_error_uses_envelope(client, auth_headers):
    resp = await client.post("/products", json={"sku": ""}, headers=auth_headers)
    body = resp.json()
    assert "data" in body
    assert "error" in body
    assert "meta" in body
    assert resp.status_code == 422


# ─── 6. client_type + credit_limit ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_credit_limit_enforced(client, auth_headers):
    """Credit sale that would exceed credit_limit_cents should be rejected."""
    p = await _product(client, auth_headers, "CL-P1", price=5000, cost=2000, stock=10)
    cli = await _client(client, auth_headers, "CL Client", credit_limit=3000)

    # First sale: 5000 > 3000 limit → rejected
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "credit" in resp.json()["error"].lower()


@pytest.mark.asyncio
async def test_credit_limit_null_means_unlimited(client, auth_headers):
    """credit_limit_cents=None means unlimited credit."""
    p = await _product(client, auth_headers, "CL-FREE-P1", price=50000, cost=2000, stock=10)
    cli = await _client(client, auth_headers, "Unlimited Client", credit_limit=None)

    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    assert resp.status_code == 201


# ─── 7. Wholesale pricing ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_distributor_gets_wholesale_price(client, auth_headers):
    """Distributor client auto-gets wholesale_price_cents."""
    p = await _product(client, auth_headers, "WH-P1", price=5000, cost=2000, wholesale=3000, stock=10)
    cli = await _client(client, auth_headers, "Distributor", client_type="distributor")

    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale = resp.json()["data"]
    assert sale["total_cents"] == 3000  # wholesale, not retail 5000


@pytest.mark.asyncio
async def test_retail_client_pays_full_price(client, auth_headers):
    """Retail client gets full price_cents, not wholesale."""
    p = await _product(client, auth_headers, "WH-RETAIL-P1", price=5000, wholesale=3000, stock=10)
    cli = await _client(client, auth_headers, "Retail Client", client_type="retail")

    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 5000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["data"]["total_cents"] == 5000


# ─── 8. Debt aging ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_debt_aging_returns_entries(client, auth_headers):
    """GET /clients/debt-aging returns per-client aging buckets."""
    p = await _product(client, auth_headers, "DA-P1", price=2000, stock=5)
    cli = await _client(client, auth_headers, "Aging Client")

    await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)

    resp = await client.get("/clients/debt-aging", headers=auth_headers)
    assert resp.status_code == 200
    entries = resp.json()["data"]
    assert isinstance(entries, list)
    assert len(entries) >= 1
    entry = next((e for e in entries if e["client_id"] == cli["id"]), None)
    assert entry is not None
    assert entry["total"] == 2000
    # Recent sale → bucket_0_30
    assert entry["bucket_0_30"] == 2000


# ─── 9. Supplier payables ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_po_payment_reduces_balance(client, auth_headers):
    """POST /suppliers/purchase-orders/{id}/payment reduces paid_cents."""
    # Create supplier
    sup_resp = await client.post("/suppliers", json={
        "name": "Ceramics Co",
    }, headers=auth_headers)
    assert sup_resp.status_code == 201
    sup_id = sup_resp.json()["data"]["id"]

    p = await _product(client, auth_headers, "PO-P1", price=5000, stock=10)

    # Create PO
    po_resp = await client.post("/suppliers/purchase-orders", json={
        "supplier_id": sup_id,
        "items": [{"product_id": p["id"], "quantity_ordered": 5, "unit_cost_cents": 2000}],
    }, headers=auth_headers)
    assert po_resp.status_code == 201
    po = po_resp.json()["data"]
    assert po["total_cents"] == 10000

    # Pay 6000
    pay_resp = await client.post(f"/suppliers/purchase-orders/{po['id']}/payment", json={
        "amount_cents": 6000,
    }, headers=auth_headers)
    assert pay_resp.status_code == 200
    paid_po = pay_resp.json()["data"]
    assert paid_po["paid_cents"] == 6000

    # Overpayment rejected
    over_resp = await client.post(f"/suppliers/purchase-orders/{po['id']}/payment", json={
        "amount_cents": 5000,
    }, headers=auth_headers)
    assert over_resp.status_code == 400


@pytest.mark.asyncio
async def test_dashboard_shows_accounts_payable(client, auth_headers):
    """Dashboard includes accounts_payable_cents."""
    resp = await client.get("/finance/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "accounts_payable_cents" in data
    assert "accounts_receivable_cents" in data


# ─── 10. Real profit / P&L ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sale_item_snapshots_unit_cost(client, auth_headers):
    """SaleItem.unit_cost_cents is set to product.cost_cents at sale time."""
    p = await _product(client, auth_headers, "COST-P1", price=5000, cost=1500, stock=5)

    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 5000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale = resp.json()["data"]
    assert sale["items"][0]["unit_cost_cents"] == 1500


@pytest.mark.asyncio
async def test_profit_loss_report(client, auth_headers):
    """GET /finance/reports/profit-loss returns P&L breakdown."""
    p = await _product(client, auth_headers, "PL-P1", price=10000, cost=4000, stock=5)
    await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 10000,
    }, headers=auth_headers)

    resp = await client.get("/finance/reports/profit-loss", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "revenue_cents" in data
    assert "cogs_cents" in data
    assert "gross_profit_cents" in data
    assert data["gross_profit_cents"] == data["revenue_cents"] - data["cogs_cents"]


# ─── 11. Stock movements ledger ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sale_creates_stock_movement(client, auth_headers):
    """Creating a sale creates a stock movement with reason=sale."""
    p = await _product(client, auth_headers, "SM-P1", stock=10)
    resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 2, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 10000,
    }, headers=auth_headers)
    assert resp.status_code == 201

    mv_resp = await client.get(f"/products/{p['id']}/movements", headers=auth_headers)
    assert mv_resp.status_code == 200
    movements = mv_resp.json()["data"]
    assert len(movements) >= 1
    sale_mv = next((m for m in movements if m["reason"] == "sale"), None)
    assert sale_mv is not None
    assert sale_mv["quantity_change"] == -2


@pytest.mark.asyncio
async def test_cancel_creates_stock_movement(client, auth_headers):
    """Cancelling a sale creates a stock movement with reason=cancel."""
    p = await _product(client, auth_headers, "SM-CANCEL-P1", stock=10)
    sale_resp = await client.post("/sales", json={
        "items": [{"product_id": p["id"], "quantity": 3, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 15000,
    }, headers=auth_headers)
    sale_id = sale_resp.json()["data"]["id"]

    # Cannot cancel — has payments (tested in phase 2), use a sale without payment
    p2 = await _product(client, auth_headers, "SM-CANCEL-P2", stock=5)
    cli = await _client(client, auth_headers, "SM Cancel Client")
    sale_resp2 = await client.post("/sales", json={
        "items": [{"product_id": p2["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    sale_id2 = sale_resp2.json()["data"]["id"]

    cancel_resp = await client.post(f"/sales/{sale_id2}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200

    mv_resp = await client.get(f"/products/{p2['id']}/movements", headers=auth_headers)
    movements = mv_resp.json()["data"]
    cancel_mv = next((m for m in movements if m["reason"] == "cancel"), None)
    assert cancel_mv is not None
    assert cancel_mv["quantity_change"] == 1
