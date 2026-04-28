import pytest


async def _create_product(client, auth_headers, sku="SALE-P1", stock=50):
    resp = await client.post("/products", json={
        "sku": sku, "name": f"Product {sku}", "price_cents": 5000,
        "cost_cents": 2000, "stock_quantity": stock, "low_stock_threshold": 5,
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_create_cash_sale(client, auth_headers):
    product = await _create_product(client, auth_headers, "CASH-001")
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 2, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 10000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale = resp.json()["data"]
    assert sale["status"] == "completed"
    assert sale["total_cents"] == 10000
    assert sale["paid_cents"] == 10000
    assert sale["balance_cents"] == 0


@pytest.mark.asyncio
async def test_stock_decremented_on_sale(client, auth_headers):
    product = await _create_product(client, auth_headers, "STOCK-DEC-001", stock=30)
    await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 5, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 25000,
    }, headers=auth_headers)
    get_resp = await client.get(f"/products/{product['id']}", headers=auth_headers)
    assert get_resp.json()["data"]["stock_quantity"] == 25


@pytest.mark.asyncio
async def test_sale_insufficient_stock_rejected(client, auth_headers):
    product = await _create_product(client, auth_headers, "INSUF-001", stock=2)
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 10, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_partial_payment_creates_partial_sale(client, auth_headers):
    product = await _create_product(client, auth_headers, "PART-001", stock=10)
    create_resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
    }, headers=auth_headers)
    sale_id = create_resp.json()["data"]["id"]

    pay_resp = await client.post(f"/sales/{sale_id}/payment", json={
        "amount_cents": 2000,
        "method": "cash",
    }, headers=auth_headers)
    assert pay_resp.status_code == 200
    sale = pay_resp.json()["data"]
    assert sale["status"] == "partial"
    assert sale["paid_cents"] == 2000
    assert sale["balance_cents"] == 3000


@pytest.mark.asyncio
async def test_overpayment_rejected(client, auth_headers):
    product = await _create_product(client, auth_headers, "OVER-001", stock=5)
    create_resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
    }, headers=auth_headers)
    sale_id = create_resp.json()["data"]["id"]

    resp = await client.post(f"/sales/{sale_id}/payment", json={
        "amount_cents": 99999,
        "method": "cash",
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_idempotent_sale(client, auth_headers):
    product = await _create_product(client, auth_headers, "IDEM-SALE-001", stock=20)
    payload = {
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "client_generated_id": "sale-idem-uuid-fixed",
    }
    r1 = await client.post("/sales", json=payload, headers=auth_headers)
    r2 = await client.post("/sales", json=payload, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
