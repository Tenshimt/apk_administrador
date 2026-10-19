import pytest


async def _create_product(client, auth_headers, sku="SALE-P1", stock=50, price=5000):
    resp = await client.post("/products", json={
        "sku": sku, "name": f"Product {sku}", "price_cents": price,
        "cost_cents": 2000, "stock_quantity": stock, "low_stock_threshold": 5,
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_client(client, auth_headers, name="Test Client"):
    resp = await client.post("/clients", json={"full_name": name, "credit_limit_cents": None}, headers=auth_headers)
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
    cli = await _create_client(client, auth_headers, "PART Client")
    create_resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    assert create_resp.status_code == 201
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
    cli = await _create_client(client, auth_headers, "OVER Client")
    create_resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    sale_id = create_resp.json()["data"]["id"]

    resp = await client.post(f"/sales/{sale_id}/payment", json={
        "amount_cents": 99999,
        "method": "cash",
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sale_response_includes_items_and_payments(client, auth_headers):
    """POST /sales response must serialize items and payments (no MissingGreenlet)."""
    product = await _create_product(client, auth_headers, "RESP-001", stock=10)
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 2, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 10000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale = resp.json()["data"]
    assert isinstance(sale["items"], list)
    assert len(sale["items"]) == 1
    assert isinstance(sale["payments"], list)
    assert len(sale["payments"]) == 1


@pytest.mark.asyncio
async def test_idempotent_sale(client, auth_headers):
    product = await _create_product(client, auth_headers, "IDEM-SALE-001", stock=20)
    cli = await _create_client(client, auth_headers, "IDEM Client")
    payload = {
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price_cents": 5000, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
        "client_generated_id": "sale-idem-uuid-fixed",
    }
    r1 = await client.post("/sales", json=payload, headers=auth_headers)
    r2 = await client.post("/sales", json=payload, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]


# ── Phase 2 tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_price_used_from_product_when_not_provided(client, auth_headers):
    """unit_price_cents is optional; product.price_cents is used if omitted."""
    product = await _create_product(client, auth_headers, "PRICE-AUTO-001", price=7500)
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 7500,
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale = resp.json()["data"]
    assert sale["total_cents"] == 7500
    assert sale["items"][0]["unit_price_cents"] == 7500


@pytest.mark.asyncio
async def test_item_discount_exceeds_gross_rejected(client, auth_headers):
    """Discount > item gross must be rejected."""
    product = await _create_product(client, auth_headers, "DISC-001", price=3000)
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 5000}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 1,
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sale_discount_exceeds_subtotal_rejected(client, auth_headers):
    """Sale-level discount > subtotal must be rejected."""
    product = await _create_product(client, auth_headers, "DISC-002", price=5000)
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 9000,
        "payment_method": "cash",
        "payment_amount_cents": 1,
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sale_without_client_rejected_when_balance_due(client, auth_headers):
    """A sale with no payment and no client_id must be rejected (balance requires client)."""
    product = await _create_product(client, auth_headers, "NOCLIENT-001")
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_debt_correct_after_partial_payment_at_creation(client, auth_headers):
    """Client debt = total - paid when sale created with partial payment."""
    product = await _create_product(client, auth_headers, "DEBT-001", price=10000)
    cli = await _create_client(client, auth_headers, "Debt Test Client")

    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
        "payment_method": "cash",
        "payment_amount_cents": 4000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale = resp.json()["data"]
    assert sale["paid_cents"] == 4000
    assert sale["balance_cents"] == 6000

    debt_resp = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp.status_code == 200
    assert debt_resp.json()["data"]["debt_cents"] == 6000


@pytest.mark.asyncio
async def test_debt_reduced_when_payment_added_to_sale(client, auth_headers):
    """Paying an existing sale reduces client.debt_cents."""
    product = await _create_product(client, auth_headers, "DEBT-PAY-001", price=8000)
    cli = await _create_client(client, auth_headers, "Debt Pay Client")

    create_resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    assert create_resp.status_code == 201
    sale_id = create_resp.json()["data"]["id"]

    # debt should be 8000 now
    debt_resp = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp.json()["data"]["debt_cents"] == 8000

    # pay 3000
    pay_resp = await client.post(f"/sales/{sale_id}/payment", json={
        "amount_cents": 3000, "method": "cash",
    }, headers=auth_headers)
    assert pay_resp.status_code == 200

    debt_resp2 = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp2.json()["data"]["debt_cents"] == 5000


@pytest.mark.asyncio
async def test_cancel_restores_stock_and_reverses_debt(client, auth_headers):
    """Cancelling an unpaid sale restores stock and reverses client debt."""
    product = await _create_product(client, auth_headers, "CANCEL-001", stock=10, price=5000)
    cli = await _create_client(client, auth_headers, "Cancel Client")

    create_resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 3, "discount_cents": 0}],
        "discount_cents": 0,
        "client_id": cli["id"],
    }, headers=auth_headers)
    assert create_resp.status_code == 201
    sale_id = create_resp.json()["data"]["id"]

    # Verify stock decremented and debt added
    prod_resp = await client.get(f"/products/{product['id']}", headers=auth_headers)
    assert prod_resp.json()["data"]["stock_quantity"] == 7
    debt_resp = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp.json()["data"]["debt_cents"] == 15000

    # Cancel the sale
    cancel_resp = await client.post(f"/sales/{sale_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["status"] == "cancelled"

    # Stock restored
    prod_resp2 = await client.get(f"/products/{product['id']}", headers=auth_headers)
    assert prod_resp2.json()["data"]["stock_quantity"] == 10

    # Debt reversed
    debt_resp2 = await client.get(f"/clients/{cli['id']}/debt", headers=auth_headers)
    assert debt_resp2.json()["data"]["debt_cents"] == 0


@pytest.mark.asyncio
async def test_cancel_blocked_if_paid(client, auth_headers):
    """A sale with payments cannot be cancelled."""
    product = await _create_product(client, auth_headers, "CANCEL-PAID-001", stock=5)
    resp = await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": 1, "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 5000,
    }, headers=auth_headers)
    assert resp.status_code == 201
    sale_id = resp.json()["data"]["id"]

    cancel_resp = await client.post(f"/sales/{sale_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 400
