"""
Seed script — creates a demo store with realistic ceramic products.
Run: python -m scripts.seed
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from database import AsyncSessionLocal, create_tables
from models.client import Client
from models.finance import Expense, ExpenseCategory
from models.product import Product, ProductUnit
from models.sale import Payment, PaymentMethod, Sale, SaleItem, SaleStatus
from models.store import Store
from models.supplier import Supplier
from models.user import User, UserRole
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Exported constant used by tests
SEED_PRODUCTS = [
    {
        "sku": "FLR-6060",
        "name": "Piso Cerámico 60x60",
        "category": "Pisos",
        "unit": ProductUnit.box,
        "m2_per_box": Decimal("1.44"),
        "price_cents": 8500,
        "cost_cents": 4200,
        "wholesale_price_cents": 6800,
        "stock_quantity": Decimal("80"),
        "low_stock_threshold": Decimal("5"),
    },
    {
        "sku": "WAL-3060",
        "name": "Revestimiento Pared 30x60",
        "category": "Paredes",
        "unit": ProductUnit.box,
        "m2_per_box": Decimal("1.08"),
        "price_cents": 6200,
        "cost_cents": 3100,
        "wholesale_price_cents": 5000,
        "stock_quantity": Decimal("60"),
        "low_stock_threshold": Decimal("5"),
    },
    {
        "sku": "PRC-6060",
        "name": "Porcelanato 60x60",
        "category": "Pisos",
        "unit": ProductUnit.box,
        "m2_per_box": Decimal("1.44"),
        "price_cents": 12000,
        "cost_cents": 6500,
        "wholesale_price_cents": 9800,
        "stock_quantity": Decimal("40"),
        "low_stock_threshold": Decimal("5"),
    },
    {
        "sku": "GRT-WHT-5KG",
        "name": "Fragua Blanca 5kg",
        "category": "Fraguas",
        "unit": ProductUnit.unit,
        "m2_per_box": None,
        "price_cents": 1800,
        "cost_cents": 900,
        "stock_quantity": Decimal("50"),
        "low_stock_threshold": Decimal("10"),
    },
    {
        "sku": "ADH-C2-25KG",
        "name": "Adhesivo Cerámico C2 25kg",
        "category": "Adhesivos",
        "unit": ProductUnit.unit,
        "m2_per_box": None,
        "price_cents": 3500,
        "cost_cents": 1750,
        "stock_quantity": Decimal("30"),
        "low_stock_threshold": Decimal("5"),
    },
    {
        "sku": "SIL-SEAL",
        "name": "Sellador Silicona",
        "category": "Adhesivos",
        "unit": ProductUnit.unit,
        "m2_per_box": None,
        "price_cents": 2200,
        "cost_cents": 1100,
        "stock_quantity": Decimal("20"),
        "low_stock_threshold": Decimal("5"),
    },
]

CLIENTS = [
    {"full_name": "María González", "phone": "+54-11-4567-8901", "email": "maria@example.com"},
    {"full_name": "Juan Rodríguez", "phone": "+54-11-2345-6789"},
    {"full_name": "Constructora Del Sur S.A.", "phone": "+54-11-9876-5432", "email": "compras@delsur.com"},
    {"full_name": "Ana López", "phone": "+54-351-456-7890"},
]


async def seed():
    await create_tables()
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        existing = (await db.execute(select(Store).where(Store.slug == "ceramica-san-martin"))).scalar_one_or_none()
        if existing:
            print("Seed already applied — skipping.")
            return

        store = Store(
            name="Ceramica San Martín",
            slug="ceramica-san-martin",
            owner_email="admin@ceramica.demo",
            currency_code="ARS",
            timezone="America/Argentina/Buenos_Aires",
        )
        db.add(store)
        await db.flush()

        owner = User(
            store_id=store.id,
            email="admin@ceramica.demo",
            hashed_password=pwd_context.hash("Admin1234!"),
            full_name="Admin Demo",
            role=UserRole.owner,
        )
        cashier = User(
            store_id=store.id,
            email="cajero@ceramica.demo",
            hashed_password=pwd_context.hash("Cajero123!"),
            full_name="Carlos Cajero",
            role=UserRole.cashier,
        )
        db.add_all([owner, cashier])
        await db.flush()

        products = []
        for p in SEED_PRODUCTS:
            # Skip if SKU already exists in this store
            ex = (await db.execute(
                select(Product).where(Product.sku == p["sku"], Product.store_id == store.id)
            )).scalar_one_or_none()
            if ex:
                products.append(ex)
                continue
            data = {k: v for k, v in p.items() if v is not None}
            product = Product(store_id=store.id, **data)
            db.add(product)
            products.append(product)
        await db.flush()

        supplier = Supplier(
            store_id=store.id,
            name="Distribuidora Cerámica Norte",
            contact_name="Pedro Suárez",
            phone="+54-11-3456-7890",
            email="ventas@ceramicanorte.com",
        )
        db.add(supplier)
        await db.flush()

        clients = []
        for c in CLIENTS:
            client = Client(store_id=store.id, **c)
            db.add(client)
            clients.append(client)
        await db.flush()

        # Demo sale
        sale1 = Sale(
            store_id=store.id,
            client_id=clients[0].id,
            cashier_id=cashier.id,
            status=SaleStatus.completed,
            subtotal_cents=17000,
            discount_cents=0,
            total_cents=17000,
            paid_cents=17000,
        )
        db.add(sale1)
        await db.flush()

        db.add(SaleItem(
            sale_id=sale1.id, product_id=products[0].id, store_id=store.id,
            quantity=Decimal("2"), unit_price_cents=8500, discount_cents=0, total_cents=17000,
        ))
        db.add(Payment(
            sale_id=sale1.id, store_id=store.id,
            amount_cents=17000, method=PaymentMethod.cash,
        ))

        db.add(Expense(
            store_id=store.id, description="Alquiler mensual",
            category=ExpenseCategory.rent, amount_cents=250000,
            recorded_by_id=owner.id,
        ))

        await db.commit()

        print("\n✓ Seed complete!")
        print("  Store slug : ceramica-san-martin")
        print("  Admin      : admin@ceramica.demo / Admin1234!")
        print("  Cashier    : cajero@ceramica.demo / Cajero123!")
        print("  API docs   : http://localhost:8000/docs\n")


if __name__ == "__main__":
    asyncio.run(seed())
