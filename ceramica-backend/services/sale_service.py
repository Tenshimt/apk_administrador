import json
import uuid
from typing import Callable, Awaitable, Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from models.audit import AuditLog
from models.client import Client
from models.product import Product
from models.sale import Payment, Sale, SaleItem, SaleStatus
from models.user import User
from schemas.sale import PaymentCreate, SaleCreate, SaleStatusUpdate

settings = get_settings()

BroadcastFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class SaleService:
    def __init__(self, db: AsyncSession, store_id: str, current_user: User | None = None) -> None:
        self.db = db
        self.store_id = store_id
        self.user = current_user

    async def list_sales(self, limit: int = 20, offset: int = 0) -> tuple[list[Sale], int]:
        from sqlalchemy import func

        q = (
            select(Sale)
            .where(Sale.store_id == self.store_id, Sale.is_active.is_(True))
            .options(selectinload(Sale.items), selectinload(Sale.payments))
            .order_by(Sale.created_at.desc())
        )
        count_q = select(func.count()).select_from(
            select(Sale).where(Sale.store_id == self.store_id, Sale.is_active.is_(True)).subquery()
        )
        total = (await self.db.execute(count_q)).scalar_one()
        sales = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(sales), total

    async def get_or_404(self, sale_id: str) -> Sale:
        result = await self.db.execute(
            select(Sale)
            .where(
                Sale.id == sale_id,
                Sale.store_id == self.store_id,
                Sale.is_active.is_(True),
            )
            .options(selectinload(Sale.items), selectinload(Sale.payments))
        )
        sale = result.scalar_one_or_none()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")
        return sale

    async def create(self, data: SaleCreate, broadcast: BroadcastFn | None = None) -> Sale:
        # Idempotency check
        if data.client_generated_id:
            result = await self.db.execute(
                select(Sale)
                .where(
                    Sale.client_generated_id == data.client_generated_id,
                    Sale.store_id == self.store_id,
                )
                .options(selectinload(Sale.items), selectinload(Sale.payments))
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        # Validate client debt limit if credit sale
        client = None
        if data.client_id:
            result = await self.db.execute(
                select(Client).where(
                    Client.id == data.client_id, Client.store_id == self.store_id
                )
            )
            client = result.scalar_one_or_none()
            if not client:
                raise HTTPException(status_code=404, detail="Client not found")

        # Build sale items and decrement stock
        sale_items = []
        subtotal = 0

        for item_data in data.items:
            result = await self.db.execute(
                select(Product).where(
                    Product.id == item_data.product_id,
                    Product.store_id == self.store_id,
                    Product.is_active.is_(True),
                )
            )
            product = result.scalar_one_or_none()
            if not product:
                raise HTTPException(
                    status_code=404, detail=f"Product {item_data.product_id} not found"
                )
            if product.stock_quantity < item_data.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for '{product.name}': "
                    f"available={product.stock_quantity}, requested={item_data.quantity}",
                )

            # Optimistic locking on stock decrement
            res = await self.db.execute(
                update(Product)
                .where(Product.id == product.id, Product.version == product.version)
                .values(
                    stock_quantity=Product.stock_quantity - item_data.quantity,
                    version=Product.version + 1,
                )
                .returning(Product.stock_quantity)
            )
            new_stock = res.scalar_one_or_none()
            if new_stock is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Concurrent update on product '{product.name}' — please retry",
                )

            item_total = item_data.unit_price_cents * item_data.quantity - item_data.discount_cents
            subtotal += item_total
            sale_items.append(
                SaleItem(
                    product_id=product.id,
                    store_id=self.store_id,
                    quantity=item_data.quantity,
                    unit_price_cents=item_data.unit_price_cents,
                    discount_cents=item_data.discount_cents,
                    total_cents=item_total,
                )
            )

            # Broadcast low stock if threshold breached
            if broadcast and new_stock <= product.low_stock_threshold:
                await broadcast(
                    self.store_id,
                    "low_stock_alert",
                    {"product_id": product.id, "sku": product.sku, "stock": new_stock},
                )

        total = subtotal - data.discount_cents

        sale = Sale(
            store_id=self.store_id,
            client_id=data.client_id,
            cashier_id=self.user.id if self.user else None,
            status=SaleStatus.pending,
            subtotal_cents=subtotal,
            discount_cents=data.discount_cents,
            total_cents=total,
            paid_cents=0,
            notes=data.notes,
            client_generated_id=data.client_generated_id,
        )
        self.db.add(sale)
        await self.db.flush()

        for item in sale_items:
            item.sale_id = sale.id
            self.db.add(item)

        # Optional immediate payment
        if data.payment_method and data.payment_amount_cents:
            await self._apply_payment(
                sale,
                client,
                PaymentCreate(
                    amount_cents=data.payment_amount_cents,
                    method=data.payment_method,
                ),
            )
        else:
            # Credit sale — add to client debt
            if client and total > 0:
                client.debt_cents += total
                sale.status = SaleStatus.partial if sale.paid_cents > 0 else SaleStatus.pending

        await self.db.flush()

        self.db.add(
            AuditLog(
                store_id=self.store_id,
                user_id=self.user.id if self.user else None,
                action="create",
                entity_type="sale",
                entity_id=sale.id,
                new_values=json.dumps({"total_cents": total, "items": len(sale_items)}),
            )
        )

        if broadcast:
            await broadcast(
                self.store_id,
                "sale_created",
                {"sale_id": sale.id, "total_cents": total, "status": sale.status.value},
            )

        # Reload with eager-loaded relationships to avoid MissingGreenlet on serialization
        result = await self.db.execute(
            select(Sale)
            .where(Sale.id == sale.id)
            .options(selectinload(Sale.items), selectinload(Sale.payments))
        )
        return result.scalar_one()

    async def update_status(self, sale_id: str, data: SaleStatusUpdate) -> Sale:
        sale = await self.get_or_404(sale_id)
        sale.status = data.status
        await self.db.flush()
        return sale

    async def add_payment(
        self, sale_id: str, data: PaymentCreate, broadcast: BroadcastFn | None = None
    ) -> Sale:
        # Idempotency
        if data.client_generated_id:
            result = await self.db.execute(
                select(Payment).where(
                    Payment.client_generated_id == data.client_generated_id,
                    Payment.store_id == self.store_id,
                )
            )
            if result.scalar_one_or_none():
                return await self.get_or_404(sale_id)

        sale = await self.get_or_404(sale_id)
        client = None
        if sale.client_id:
            result = await self.db.execute(select(Client).where(Client.id == sale.client_id))
            client = result.scalar_one_or_none()

        await self._apply_payment(sale, client, data)
        await self.db.flush()

        if broadcast:
            await broadcast(
                self.store_id,
                "payment_received",
                {
                    "sale_id": sale.id,
                    "amount_cents": data.amount_cents,
                    "balance_cents": sale.balance_cents,
                },
            )

        # Reload with eager-loaded relationships to avoid MissingGreenlet on serialization
        result = await self.db.execute(
            select(Sale)
            .where(Sale.id == sale.id)
            .options(selectinload(Sale.items), selectinload(Sale.payments))
        )
        return result.scalar_one()

    async def _apply_payment(
        self, sale: Sale, client: Client | None, data: PaymentCreate
    ) -> None:
        if data.amount_cents > sale.balance_cents:
            raise HTTPException(
                status_code=400,
                detail=f"Payment exceeds balance. Balance: {sale.balance_cents} cents",
            )

        payment = Payment(
            sale_id=sale.id,
            store_id=self.store_id,
            amount_cents=data.amount_cents,
            method=data.method,
            reference=data.reference,
            notes=data.notes,
            client_generated_id=getattr(data, "client_generated_id", None),
        )
        self.db.add(payment)
        sale.paid_cents += data.amount_cents

        if client:
            client.debt_cents = max(0, client.debt_cents - data.amount_cents)

        if sale.paid_cents >= sale.total_cents:
            sale.status = SaleStatus.completed
        elif sale.paid_cents > 0:
            sale.status = SaleStatus.partial
