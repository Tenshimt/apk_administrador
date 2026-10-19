"""Phase 4 regression tests: fractional quantities, unit/m2_per_box, seed data."""
import math
import pytest
from decimal import Decimal


async def _create_product(client, auth_headers, sku="P4-001", stock=50,
                          unit="unit", m2_per_box=None, wholesale_price_cents=None):
    body = {
        "sku": sku,
        "name": f"Product {sku}",
        "price_cents": 5000,
        "cost_cents": 2000,
        "stock_quantity": stock,
        "low_stock_threshold": 5,
        "unit": unit,
    }
    if m2_per_box is not None:
        body["m2_per_box"] = str(m2_per_box)
    if wholesale_price_cents is not None:
        body["wholesale_price_cents"] = wholesale_price_cents
    resp = await client.post("/products", json=body, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ─── Item 1: fractional stock and sale quantities ────────────────────────────

@pytest.mark.asyncio
async def test_product_fractional_stock(client, auth_headers):
    """Product can be created with fractional stock_quantity."""
    resp = await client.post("/products", json={
        "sku": "FRAC-001",
        "name": "Fractional Product",
        "price_cents": 3000,
        "cost_cents": 1500,
        "stock_quantity": "12.5",
        "low_stock_threshold": "2.5",
        "unit": "m2",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert Decimal(str(data["stock_quantity"])) == Decimal("12.5")


@pytest.mark.asyncio
async def test_sale_fractional_quantity(client, auth_headers):
    """SaleItem.quantity can be a Decimal (e.g. 2.5)."""
    product = await _create_product(client, auth_headers, "FRAC-SALE-001", stock="20")
    resp = await client.post("/sales", json={
        "items": [{
            "product_id": product["id"],
            "quantity": "2.5",
            "discount_cents": 0,
        }],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": int(round(2.5 * 5000)),
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    sale = resp.json()["data"]
    item = sale["items"][0]
    assert Decimal(str(item["quantity"])) == Decimal("2.5")
    assert sale["total_cents"] == int(round(Decimal("2.5") * 5000))


@pytest.mark.asyncio
async def test_stock_decremented_fractionally(client, auth_headers):
    """Stock decrements by the fractional quantity sold."""
    product = await _create_product(client, auth_headers, "FRAC-STOCK-001", stock="10.0")
    await client.post("/sales", json={
        "items": [{"product_id": product["id"], "quantity": "3.5", "discount_cents": 0}],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": int(round(Decimal("3.5") * 5000)),
    }, headers=auth_headers)
    r = await client.get(f"/products/{product['id']}", headers=auth_headers)
    remaining = Decimal(str(r.json()["data"]["stock_quantity"]))
    assert remaining == Decimal("6.5")


# ─── Item 2: unit + m2_per_box + m² → boxes conversion ───────────────────────

@pytest.mark.asyncio
async def test_product_has_unit_and_m2_per_box(client, auth_headers):
    """Products expose unit and m2_per_box fields."""
    product = await _create_product(
        client, auth_headers, "UNIT-001", stock="50",
        unit="box", m2_per_box="1.44"
    )
    assert product["unit"] == "box"
    assert Decimal(str(product["m2_per_box"])) == Decimal("1.44")


@pytest.mark.asyncio
async def test_m2_to_boxes_conversion(client, auth_headers):
    """Requesting 5.0 m² of a box product (1.44 m²/box) → ceil(5/1.44)=4 boxes."""
    product = await _create_product(
        client, auth_headers, "M2BOX-001", stock="20",
        unit="box", m2_per_box="1.44"
    )
    boxes_needed = math.ceil(Decimal("5.0") / Decimal("1.44"))  # 4
    expected_total = int(round(Decimal(str(boxes_needed)) * 5000))

    resp = await client.post("/sales", json={
        "items": [{
            "product_id": product["id"],
            "quantity": "1",        # overridden by requested_m2
            "requested_m2": "5.0",
            "discount_cents": 0,
        }],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": expected_total,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    sale = resp.json()["data"]
    item = sale["items"][0]
    assert Decimal(str(item["quantity"])) == Decimal(str(boxes_needed))
    assert Decimal(str(item["requested_m2"])) == Decimal("5.0")
    assert sale["total_cents"] == expected_total


@pytest.mark.asyncio
async def test_m2_conversion_rounds_up(client, auth_headers):
    """1.0 m² at 1.44 m²/box → ceil(1.0/1.44) = 1 box (not 0)."""
    product = await _create_product(
        client, auth_headers, "M2BOX-CEIL-001", stock="10",
        unit="box", m2_per_box="1.44"
    )
    resp = await client.post("/sales", json={
        "items": [{
            "product_id": product["id"],
            "quantity": "1",
            "requested_m2": "1.0",
            "discount_cents": 0,
        }],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 5000,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    item = resp.json()["data"]["items"][0]
    assert Decimal(str(item["quantity"])) == Decimal("1")


@pytest.mark.asyncio
async def test_non_box_product_ignores_requested_m2(client, auth_headers):
    """requested_m2 is ignored for products with unit != 'box'."""
    product = await _create_product(client, auth_headers, "UNIT-IGN-001", stock="10", unit="unit")
    resp = await client.post("/sales", json={
        "items": [{
            "product_id": product["id"],
            "quantity": "2",
            "requested_m2": "5.0",
            "discount_cents": 0,
        }],
        "discount_cents": 0,
        "payment_method": "cash",
        "payment_amount_cents": 10000,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    item = resp.json()["data"]["items"][0]
    assert Decimal(str(item["quantity"])) == Decimal("2")


# ─── Item 3: seed data ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_creates_ceramic_products(client, auth_headers):
    """Seed inserts realistic ceramic products with unit/m2_per_box."""
    from scripts.seed import SEED_PRODUCTS
    expected_skus = {p["sku"] for p in SEED_PRODUCTS}

    # POST each product
    for p in SEED_PRODUCTS:
        body = {**p}
        # Convert Decimal fields to str for JSON
        for k in ("stock_quantity", "low_stock_threshold", "m2_per_box"):
            if k in body and body[k] is not None:
                body[k] = str(body[k])
        resp = await client.post("/products", json=body, headers=auth_headers)
        assert resp.status_code in (201, 409), f"Unexpected {resp.status_code} for {p['sku']}: {resp.text}"

    # Verify all skus exist
    resp = await client.get("/products?limit=50", headers=auth_headers)
    assert resp.status_code == 200
    skus = {p["sku"] for p in resp.json()["data"]}
    assert expected_skus.issubset(skus)
