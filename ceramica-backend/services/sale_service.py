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
from models.user import User, UserRole
from schemas.sale import PaymentCreate, SaleCreate, SaleStatusUpdate

settings = get_settings()

BroadcastFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]

_PRIVILEGED = {UserRole.owner, UserRole.admin}


class SaleService:
    def __init__(self, db: AsyncSession, store_id: str, current_user: User | None = None) -> None:
        self.db = db
        self.store_id = store_id
        self.user = current_user

    def _require_privileged(self) -> None:
        if not self.user or self.user.role not in _PRIVILEGED:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

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

            # Price comes from product; override allowed only for owner/admin
            if item_data.unit_price_cents is not None and item_data.unit_price_cents != product.price_cents:
                self._require_privileged()
                unit_price = item_data.unit_price_cents
            else:
                unit_price = product.price_cents

            item_gross = unit_price * item_data.quantity
            if item_data.discount_cents > item_gross:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item discount ({item_data.discount_cents}) exceeds item gross ({item_gross})",
                )
            item_total = item_gross - item_data.discount_cents

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

            subtotal += item_total
            sale_items.append(
                SaleItem(
                    product_id=product.id,
                    store_id=self.store_id,
                    quantity=item_data.quantity,
                    unit_price_cents=unit_price,
                    discount_cents=item_data.discount_cents,
                    total_cents=item_total,
                )
            )

            if broadcast and new_stock <= product.low_stock_threshold:
                await broadcast(
                    self.store_id,
                    "low_stock_alert",
                    {"product_id": product.id, "sku": product.sku, "stock": new_stock},
                )

        if data.discount_cents > subtotal:
            raise HTTPException(
                status_code=400,
                detail=f"Sale discount ({data.discount_cents}) exceeds subtotal ({subtotal})",
            )
        total = subtotal - data.discount_cents
        if total < 0:
            raise HTTPException(status_code=400, detail="Sale total cannot be negative")

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
                PaymentCreate(
                    amount_cents=data.payment_amount_cents,
                    method=data.payment_method,
                ),
            )

        # Remaining balance goes to client debt; require client_id if balance > 0
        remaining = total - sale.paid_cents
        if remaining > 0:
            if not client:
                raise HTTPException(
                    status_code=400,
                    detail="client_id is required when sale has an unpaid balance",
                )
            client.debt_cents += remaining

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

        result = await self.db.execute(
            select(Sale)
            .where(Sale.id == sale.id)
            .options(selectinload(Sale.items), selectinload(Sale.payments))
        )
        return result.scalar_one()

    async def cancel(self, sale_id: str, broadcast: BroadcastFn | None = None) -> Sale:
        self._require_privileged()
        sale = await self.get_or_404(sale_id)

        if sale.status == SaleStatus.cancelled:
            raise HTTPException(status_code=400, detail="Sale is already cancelled")
        if sale.paid_cents > 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel a sale with payments. Record a refund first.",
            )

        # Restore stock for each item
        for item in sale.items:
            await self.db.execute(
                update(Product)
                .where(Product.id == item.product_id)
                .values(stock_quantity=Product.stock_quantity + item.quantity)
            )

        # Reverse client debt (only the unpaid balance)
        if sale.client_id and sale.balance_cents > 0:
            result = await self.db.execute(
                select(Client).where(Client.id == sale.client_id)
            )
            cl = result.scalar_one_or_none()
            if cl:
                cl.debt_cents = max(0, cl.debt_cents - sale.balance_cents)

        sale.status = SaleStatus.cancelled
        self.db.add(
            AuditLog(
                store_id=self.store_id,
                user_id=self.user.id if self.user else None,
                action="cancel",
                entity_type="sale",
                entity_id=sale.id,
                new_values=json.dumps({"cancelled_total": sale.total_cents}),
            )
        )
        await self.db.flush()

        if broadcast:
            await broadcast(
                self.store_id,
                "sale_cancelled",
                {"sale_id": sale.id, "total_cents": sale.total_cents},
            )

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

        await self._apply_payment(sale, data)

        # Reduce client debt by amount paid
        if client:
            client.debt_cents = max(0, client.debt_cents - data.amount_cents)

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

        result = await self.db.execute(
            select(Sale)
            .where(Sale.id == sale.id)
            .options(selectinload(Sale.items), selectinload(Sale.payments))
        )
        return result.scalar_one()

    async def _apply_payment(self, sale: Sale, data: PaymentCreate) -> None:
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

        if sale.paid_cents >= sale.total_cents:
            sale.status = SaleStatus.completed
        elif sale.paid_cents > 0:
            sale.status = SaleStatus.partial
