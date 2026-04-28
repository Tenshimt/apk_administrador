"""
Seed script — creates a demo store with realistic data.
Run: python -m scripts.seed
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import AsyncSessionLocal, create_tables
from models.client import Client
from models.finance import Expense, ExpenseCategory
from models.product import Product
from models.sale import Payment, PaymentMethod, Sale, SaleItem, SaleStatus
from models.store import Store
from models.supplier import Supplier
from models.user import User, UserRole
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PRODUCTS = [
    {"sku": "CER-001", "name": "Azulejo Artesanal 20x20", "category": "Azulejos", "price_cents": 2500, "cost_cents": 1200, "stock_quantity": 150},
    {"sku": "CER-002", "name": "Porcelanato Marmolado 60x60", "category": "Porcelanato", "price_cents": 8900, "cost_cents": 4500, "stock_quantity": 80},
    {"sku": "CER-003", "name": "Mosaico Veneciano Mix", "category": "Mosaicos", "price_cents": 3200, "cost_cents": 1600, "stock_quantity": 3, "low_stock_threshold": 10},
    {"sku": "CER-004", "name": "Cerámica Rústica 45x45", "category": "Cerámica", "price_cents": 4100, "cost_cents": 2000, "stock_quantity": 60},
    {"sku": "CER-005", "name": "Porcelanato Madera 20x120", "category": "Porcelanato", "price_cents": 12000, "cost_cents": 7000, "stock_quantity": 45},
    {"sku": "ADH-001", "name": "Adhesivo Cerámico 25kg", "category": "Adhesivos", "price_cents": 1800, "cost_cents": 900, "stock_quantity": 2, "low_stock_threshold": 5},
    {"sku": "FUG-001", "name": "Fragua Blanca 5kg", "category": "Fraguas", "price_cents": 900, "cost_cents": 400, "stock_quantity": 30},
    {"sku": "CER-006", "name": "Cerámica Exterior Anti-deslizante 30x30", "category": "Cerámica", "price_cents": 3500, "cost_cents": 1800, "stock_quantity": 90},
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
        # Store + owner
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

        # Products
        products = []
        for p in PRODUCTS:
            product = Product(store_id=store.id, **p)
            db.add(product)
            products.append(product)
        await db.flush()

        # Supplier
        supplier = Supplier(
            store_id=store.id,
            name="Distribuidora Cerámica Norte",
            contact_name="Pedro Suárez",
            phone="+54-11-3456-7890",
            email="ventas@ceramicanorte.com",
        )
        db.add(supplier)
        await db.flush()

        # Clients
        clients = []
        for c in CLIENTS:
            client = Client(store_id=store.id, **c)
            db.add(client)
            clients.append(client)
        await db.flush()

        # Sales
        sale1 = Sale(
            store_id=store.id,
            client_id=clients[0].id,
            cashier_id=cashier.id,
            status=SaleStatus.completed,
            subtotal_cents=17800,
            discount_cents=0,
            total_cents=17800,
            paid_cents=17800,
        )
        db.add(sale1)
        await db.flush()

        db.add(SaleItem(
            sale_id=sale1.id, product_id=products[0].id, store_id=store.id,
            quantity=5, unit_price_cents=2500, discount_cents=0, total_cents=12500,
        ))
        db.add(SaleItem(
            sale_id=sale1.id, product_id=products[6].id, store_id=store.id,
            quantity=3, unit_price_cents=900, discount_cents=0, total_cents=2700,
        ))
        db.add(Payment(
            sale_id=sale1.id, store_id=store.id,
            amount_cents=17800, method=PaymentMethod.cash,
        ))

        # Pending/credit sale
        sale2 = Sale(
            store_id=store.id,
            client_id=clients[2].id,
            cashier_id=cashier.id,
            status=SaleStatus.partial,
            subtotal_cents=89000,
            discount_cents=5000,
            total_cents=84000,
            paid_cents=40000,
        )
        db.add(sale2)
        await db.flush()

        clients[2].debt_cents = 44000
        db.add(SaleItem(
            sale_id=sale2.id, product_id=products[1].id, store_id=store.id,
            quantity=10, unit_price_cents=8900, discount_cents=5000, total_cents=84000,
        ))
        db.add(Payment(
            sale_id=sale2.id, store_id=store.id,
            amount_cents=40000, method=PaymentMethod.transfer, reference="TRF-2024-001",
        ))

        # Expenses
        db.add(Expense(
            store_id=store.id, description="Alquiler mensual enero",
            category=ExpenseCategory.rent, amount_cents=250000,
            recorded_by_id=owner.id,
        ))
        db.add(Expense(
            store_id=store.id, description="Luz y gas",
            category=ExpenseCategory.utilities, amount_cents=35000,
            recorded_by_id=owner.id,
        ))

        await db.commit()

        print(f"\n✓ Seed complete!")
        print(f"  Store slug : ceramica-san-martin")
        print(f"  Admin      : admin@ceramica.demo / Admin1234!")
        print(f"  Cashier    : cajero@ceramica.demo / Cajero123!")
        print(f"  API docs   : http://localhost:8000/docs\n")


if __name__ == "__main__":
    asyncio.run(seed())
