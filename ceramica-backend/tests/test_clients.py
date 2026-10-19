import pytest


async def _create_product(client, auth_headers, sku, stock=20, price=5000):
    resp = await client.post("/products", json={
        "sku": sku, "name": f"Product {sku}", "price_cents": price,
        "cost_cents": 2000, "stock_quantity": stock, "low_stock_threshold": 5,
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_client(client, auth_headers, name):
    resp = await client.post("/clients", json={"full_name": name, "credit_limit_cents": None}, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_credit_sale(client, auth_headers, product_id, client_id, quantity=1):
    resp = await client.post("/sales", json={
        "items": [{"product_id": product_id, "quantity": quantity, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": client_id,
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["data"]


@pytest.mark.asyncio
async def test_fifo_payment_distributes_across_sales(client, auth_headers):
    """POST /clients/{id}/payment distributes FIFO across unpaid sales."""
    p1 = await _create_product(client, auth_headers, "FIFO-P1", stock=10, price=3000)
    p2 = await _create_product(client, auth_headers, "FIFO-P2", stock=10, price=4000)
    cli = await _create_client(client, auth_headers, "FIFO Client")

    sale1 = await _create_credit_sale(client, auth_headers, p1["id"], cli["id"])
    sale2 = await _create_credit_sale(client, auth_headers, p2["id"], cli["id"])

    # Total debt: 7000 (3000 + 4000)
    debt_resp = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp.json()["data"]["debt_cents"] == 7000

    # Pay 5000: should clear sale1 (3000) and partially pay sale2 (2000)
    pay_resp = await client.post(f"/clients/{cli['id']}/payment", json={
        "amount_cents": 5000,
        "method": "cash",
    }, headers=auth_headers)
    assert pay_resp.status_code == 200

    # sale1 should be completed, sale2 should be partial
    s1_resp = await client.get(f"/sales/{sale1['id']}", headers=auth_headers)
    s2_resp = await client.get(f"/sales/{sale2['id']}", headers=auth_headers)
    assert s1_resp.json()["data"]["status"] == "completed"
    assert s2_resp.json()["data"]["status"] == "partial"
    assert s2_resp.json()["data"]["paid_cents"] == 2000

    # Remaining debt: 2000
    debt_resp2 = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp2.json()["data"]["debt_cents"] == 2000


@pytest.mark.asyncio
async def test_fifo_payment_exceeds_debt_rejected(client, auth_headers):
    """Payment exceeding total client debt must be rejected."""
    p = await _create_product(client, auth_headers, "FIFO-EX-P1", stock=5, price=3000)
    cli = await _create_client(client, auth_headers, "FIFO Excess Client")

    await _create_credit_sale(client, auth_headers, p["id"], cli["id"])

    pay_resp = await client.post(f"/clients/{cli['id']}/payment", json={
        "amount_cents": 99999,
        "method": "cash",
    }, headers=auth_headers)
    assert pay_resp.status_code == 400
