import json

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.audit import AuditLog
from models.product import Product
from models.user import User
from schemas.product import ProductCreate, ProductUpdate, StockAdjustRequest

settings = get_settings()


class ProductService:
    def __init__(self, db: AsyncSession, store_id: str, current_user: User | None = None) -> None:
        self.db = db
        self.store_id = store_id
        self.user = current_user

    async def list_products(
        self,
        limit: int = 20,
        offset: int = 0,
        category: str | None = None,
        search: str | None = None,
        low_stock_only: bool = False,
    ) -> tuple[list[Product], int]:
        q = select(Product).where(
            Product.store_id == self.store_id, Product.is_active.is_(True)
        )
        if category:
            q = q.where(Product.category == category)
        if search:
            q = q.where(Product.name.ilike(f"%{search}%"))
        if low_stock_only:
            q = q.where(Product.stock_quantity <= Product.low_stock_threshold)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()
        products = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(products), total

    async def get_or_404(self, product_id: str) -> Product:
        result = await self.db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.store_id == self.store_id,
                Product.is_active.is_(True),
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return product

    async def create(self, data: ProductCreate) -> Product:
        # Idempotency — deduplicate by client_generated_id
        if data.client_generated_id:
            result = await self.db.execute(
                select(Product).where(
                    Product.client_generated_id == data.client_generated_id,
                    Product.store_id == self.store_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        # SKU uniqueness within store
        result = await self.db.execute(
            select(Product).where(
                Product.sku == data.sku,
                Product.store_id == self.store_id,
                Product.is_active.is_(True),
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"SKU '{data.sku}' already exists")

        product = Product(**data.model_dump(), store_id=self.store_id)
        self.db.add(product)
        await self.db.flush()
        await self._audit("create", product.id, None, data.model_dump())
        return product

    async def update(self, product_id: str, data: ProductUpdate) -> Product:
        product = await self.get_or_404(product_id)
        old = {k: getattr(product, k) for k in data.model_fields_set}
        changes = data.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(product, key, value)
        await self.db.flush()
        await self._audit("update", product.id, old, changes)
        return product

    async def delete(self, product_id: str) -> None:
        product = await self.get_or_404(product_id)
        product.is_active = False
        await self._audit("delete", product.id, {"is_active": True}, {"is_active": False})

    async def adjust_stock(
        self, product_id: str, data: StockAdjustRequest, *, broadcast_fn=None
    ) -> Product:
        """Adjust stock with optimistic locking to prevent race conditions."""
        product = await self.get_or_404(product_id)
        new_qty = product.stock_quantity + data.quantity_delta
        if new_qty < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock. Available: {product.stock_quantity}",
            )

        # Optimistic locking — WHERE version = current prevents concurrent overwrites
        result = await self.db.execute(
            update(Product)
            .where(Product.id == product_id, Product.version == product.version)
            .values(stock_quantity=new_qty, version=Product.version + 1)
            .returning(Product.version)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Concurrent stock update detected — please retry",
            )

        await self.db.refresh(product)
        await self._audit(
            "stock_adjust",
            product.id,
            {"stock_quantity": product.stock_quantity - data.quantity_delta},
            {"stock_quantity": new_qty, "reason": data.reason},
        )

        if broadcast_fn and product.stock_quantity <= product.low_stock_threshold:
            await broadcast_fn(
                self.store_id,
                "low_stock_alert",
                {"product_id": product.id, "sku": product.sku, "stock": product.stock_quantity},
            )

        return product

    async def _audit(
        self,
        action: str,
        entity_id: str,
        old_values: dict | None,
        new_values: dict | None,
    ) -> None:
        log = AuditLog(
            store_id=self.store_id,
            user_id=self.user.id if self.user else None,
            action=action,
            entity_type="product",
            entity_id=entity_id,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
        )
        self.db.add(log)
