import pytest


@pytest.mark.asyncio
async def test_create_product(client, auth_headers):
    payload = {
        "sku": "TEST-001",
        "name": "Azulejo Test 20x20",
        "category": "Azulejos",
        "price_cents": 2500,
        "cost_cents": 1200,
        "stock_quantity": 100,
        "low_stock_threshold": 10,
    }
    resp = await client.post("/products", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["sku"] == "TEST-001"
    assert data["price_cents"] == 2500
    assert data["stock_quantity"] == 100


@pytest.mark.asyncio
async def test_duplicate_sku_rejected(client, auth_headers):
    payload = {
        "sku": "DUP-001", "name": "A", "price_cents": 100,
        "cost_cents": 50, "stock_quantity": 10, "low_stock_threshold": 2,
    }
    await client.post("/products", json=payload, headers=auth_headers)
    resp = await client.post("/products", json=payload, headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_products(client, auth_headers):
    resp = await client.get("/products", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_idempotent_create(client, auth_headers):
    payload = {
        "sku": "IDEM-001", "name": "Idempotent", "price_cents": 500,
        "cost_cents": 200, "stock_quantity": 5, "low_stock_threshold": 1,
        "client_generated_id": "fixed-uuid-1234",
    }
    r1 = await client.post("/products", json=payload, headers=auth_headers)
    r2 = await client.post("/products", json=payload, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]


@pytest.mark.asyncio
async def test_adjust_stock(client, auth_headers):
    create_resp = await client.post("/products", json={
        "sku": "ADJ-001", "name": "Adjustable", "price_cents": 1000,
        "cost_cents": 500, "stock_quantity": 20, "low_stock_threshold": 5,
    }, headers=auth_headers)
    product_id = create_resp.json()["data"]["id"]

    resp = await client.post(
        f"/products/{product_id}/adjust-stock",
        json={"quantity_delta": -5, "reason": "damaged"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["stock_quantity"] == 15


@pytest.mark.asyncio
async def test_adjust_stock_below_zero_rejected(client, auth_headers):
    create_resp = await client.post("/products", json={
        "sku": "ADJ-002", "name": "Limited", "price_cents": 1000,
        "cost_cents": 500, "stock_quantity": 3, "low_stock_threshold": 1,
    }, headers=auth_headers)
    product_id = create_resp.json()["data"]["id"]

    resp = await client.post(
        f"/products/{product_id}/adjust-stock",
        json={"quantity_delta": -10, "reason": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_soft_delete(client, auth_headers):
    create_resp = await client.post("/products", json={
        "sku": "DEL-001", "name": "To Delete", "price_cents": 500,
        "cost_cents": 200, "stock_quantity": 5, "low_stock_threshold": 1,
    }, headers=auth_headers)
    product_id = create_resp.json()["data"]["id"]

    del_resp = await client.delete(f"/products/{product_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    get_resp = await client.get(f"/products/{product_id}", headers=auth_headers)
    assert get_resp.status_code == 404
