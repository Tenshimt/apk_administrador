from typing import Callable, Awaitable, Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.product import Product
from models.stock_movement import MovementReason, StockMovement
from models.supplier import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderPayment,
    PurchaseOrderStatus,
    Supplier,
)
from models.user import User
from schemas.supplier import PurchaseOrderCreate, PurchaseOrderReceive, SupplierCreate

BroadcastFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]


class SupplierService:
    def __init__(self, db: AsyncSession, store_id: str, current_user: User | None = None) -> None:
        self.db = db
        self.store_id = store_id
        self.user = current_user

    async def list_suppliers(self, limit: int = 20, offset: int = 0) -> tuple[list[Supplier], int]:
        q = select(Supplier).where(
            Supplier.store_id == self.store_id, Supplier.is_active.is_(True)
        )
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        suppliers = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(suppliers), total

    async def create_supplier(self, data: SupplierCreate) -> Supplier:
        supplier = Supplier(**data.model_dump(), store_id=self.store_id)
        self.db.add(supplier)
        await self.db.flush()
        return supplier

    async def create_purchase_order(self, data: PurchaseOrderCreate) -> PurchaseOrder:
        if data.client_generated_id:
            result = await self.db.execute(
                select(PurchaseOrder).where(
                    PurchaseOrder.client_generated_id == data.client_generated_id,
                    PurchaseOrder.store_id == self.store_id,
                )
            )
            if existing := result.scalar_one_or_none():
                return existing

        result = await self.db.execute(
            select(Supplier).where(
                Supplier.id == data.supplier_id, Supplier.store_id == self.store_id
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Supplier not found")

        order = PurchaseOrder(
            store_id=self.store_id,
            supplier_id=data.supplier_id,
            ordered_by_id=self.user.id if self.user else None,
            notes=data.notes,
            client_generated_id=data.client_generated_id,
        )
        self.db.add(order)
        await self.db.flush()

        total = 0
        for item_data in data.items:
            result = await self.db.execute(
                select(Product).where(
                    Product.id == item_data.product_id, Product.store_id == self.store_id
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(
                    status_code=404, detail=f"Product {item_data.product_id} not found"
                )
            item_total = item_data.quantity_ordered * item_data.unit_cost_cents
            total += item_total
            self.db.add(
                PurchaseOrderItem(
                    order_id=order.id,
                    product_id=item_data.product_id,
                    store_id=self.store_id,
                    quantity_ordered=item_data.quantity_ordered,
                    unit_cost_cents=item_data.unit_cost_cents,
                    total_cents=item_total,
                )
            )
        order.total_cents = total
        await self.db.flush()
        result = await self.db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == order.id)
            .options(selectinload(PurchaseOrder.items))
        )
        return result.scalar_one()

    async def receive_order(
        self, order_id: str, data: PurchaseOrderReceive, broadcast: BroadcastFn | None = None
    ) -> PurchaseOrder:
        result = await self.db.execute(
            select(PurchaseOrder)
            .where(
                PurchaseOrder.id == order_id,
                PurchaseOrder.store_id == self.store_id,
                PurchaseOrder.status.in_([PurchaseOrderStatus.draft, PurchaseOrderStatus.sent]),
            )
            .options(selectinload(PurchaseOrder.items))
        )
        order = result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Purchase order not found or already received")

        item_map = {item.id: item for item in order.items}
        received_products = []

        for recv in data.items:
            item = item_map.get(recv["item_id"])
            if not item:
                raise HTTPException(status_code=404, detail=f"Order item {recv['item_id']} not found")
            qty = recv["quantity_received"]
            if qty <= 0:
                continue
            item.quantity_received += qty

            result = await self.db.execute(
                select(Product).where(Product.id == item.product_id)
            )
            product = result.scalar_one()
            await self.db.execute(
                update(Product)
                .where(Product.id == product.id)
                .values(
                    stock_quantity=Product.stock_quantity + qty,
                    version=Product.version + 1,
                )
            )
            self.db.add(StockMovement(
                store_id=self.store_id,
                product_id=product.id,
                quantity_change=qty,
                reason=MovementReason.purchase,
                reference_id=order.id,
                user_id=self.user.id if self.user else None,
            ))
            received_products.append(
                {"product_id": product.id, "sku": product.sku, "quantity": qty}
            )

        all_received = all(
            i.quantity_received >= i.quantity_ordered for i in order.items
        )
        order.status = PurchaseOrderStatus.received if all_received else PurchaseOrderStatus.sent

        await self.db.flush()

        if broadcast:
            await broadcast(
                self.store_id,
                "purchase_received",
                {"order_id": order.id, "products": received_products},
            )

        return order

    async def add_payment(self, order_id: str, amount_cents: int, notes: str | None) -> PurchaseOrder:
        result = await self.db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == order_id, PurchaseOrder.store_id == self.store_id)
            .options(selectinload(PurchaseOrder.items))
        )
        order = result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Purchase order not found")

        balance = order.total_cents - order.paid_cents
        if amount_cents > balance:
            raise HTTPException(
                status_code=400,
                detail=f"Payment ({amount_cents}) exceeds PO balance ({balance})",
            )

        self.db.add(PurchaseOrderPayment(
            order_id=order.id,
            store_id=self.store_id,
            amount_cents=amount_cents,
            notes=notes,
        ))
        order.paid_cents += amount_cents
        await self.db.flush()
        result = await self.db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == order.id)
            .options(selectinload(PurchaseOrder.items))
        )
        return result.scalar_one()

    async def list_purchase_orders(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[PurchaseOrder], int]:
        q = (
            select(PurchaseOrder)
            .where(
                PurchaseOrder.store_id == self.store_id, PurchaseOrder.is_active.is_(True)
            )
            .options(selectinload(PurchaseOrder.items))
            .order_by(PurchaseOrder.created_at.desc())
        )
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        orders = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(orders), total
