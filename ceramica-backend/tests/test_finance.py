import pytest


@pytest.mark.asyncio
async def test_dashboard_returns_data(client, auth_headers):
    resp = await client.get("/finance/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "revenue_cents" in data
    assert "expenses_cents" in data
    assert "profit_cents" in data
    assert "sales_count" in data
    assert "pending_debt_cents" in data
    assert "low_stock_count" in data


@pytest.mark.asyncio
async def test_create_expense(client, auth_headers):
    resp = await client.post("/finance/expense", json={
        "description": "Alquiler enero",
        "category": "rent",
        "amount_cents": 300000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["amount_cents"] == 300000
    assert data["category"] == "rent"


@pytest.mark.asyncio
async def test_expense_idempotency(client, auth_headers):
    payload = {
        "description": "Luz y gas",
        "category": "utilities",
        "amount_cents": 50000,
        "client_generated_id": "expense-idem-uuid-001",
    }
    r1 = await client.post("/finance/expense", json=payload, headers=auth_headers)
    r2 = await client.post("/finance/expense", json=payload, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]


@pytest.mark.asyncio
async def test_cashflow(client, auth_headers):
    resp = await client.get("/finance/cashflow", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "revenue_cents" in data
    assert "expenses_cents" in data
    assert "net_cents" in data


@pytest.mark.asyncio
async def test_inventory_valuation(client, auth_headers):
    # Create a product first
    await client.post("/products", json={
        "sku": "VAL-001", "name": "Valuation Test", "price_cents": 5000,
        "cost_cents": 2000, "stock_quantity": 10, "low_stock_threshold": 2,
    }, headers=auth_headers)
    resp = await client.get("/finance/reports/inventory-valuation", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["product_count"] >= 1
    assert "cost_value_cents" in data
    assert "retail_value_cents" in data
