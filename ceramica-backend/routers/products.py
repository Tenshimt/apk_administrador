from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user, require_roles
from dependencies.store import get_store_id
from models.stock_movement import StockMovement
from models.user import User, UserRole
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.product import ProductCreate, ProductOut, ProductUpdate, StockAdjustRequest, StockMovementOut
from services.product_service import ProductService
from websocket_manager import manager

router = APIRouter(prefix="/products", tags=["products"])

_privileged = Depends(require_roles(UserRole.owner, UserRole.admin))


def _svc(
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    user: User = Depends(get_current_user),
) -> ProductService:
    return ProductService(db, store_id, user)


@router.get("", response_model=PaginatedResponse[ProductOut])
async def list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: str | None = None,
    search: str | None = None,
    svc: ProductService = Depends(_svc),
):
    products, total = await svc.list_products(
        limit=limit, offset=offset, category=category, search=search
    )
    return PaginatedResponse(
        data=[ProductOut.model_validate(p) for p in products],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.get("/low-stock", response_model=PaginatedResponse[ProductOut])
async def low_stock(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: ProductService = Depends(_svc),
):
    products, total = await svc.list_products(limit=limit, offset=offset, low_stock_only=True)
    return PaginatedResponse(
        data=[ProductOut.model_validate(p) for p in products],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.post("", response_model=StandardResponse[ProductOut], status_code=201, dependencies=[_privileged])
async def create_product(data: ProductCreate, svc: ProductService = Depends(_svc)):
    product = await svc.create(data)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.get("/{product_id}", response_model=StandardResponse[ProductOut])
async def get_product(product_id: str, svc: ProductService = Depends(_svc)):
    product = await svc.get_or_404(product_id)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.put("/{product_id}", response_model=StandardResponse[ProductOut], dependencies=[_privileged])
async def update_product(
    product_id: str, data: ProductUpdate, svc: ProductService = Depends(_svc)
):
    product = await svc.update(product_id, data)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.delete("/{product_id}", response_model=StandardResponse[dict], dependencies=[_privileged])
async def delete_product(product_id: str, svc: ProductService = Depends(_svc)):
    await svc.delete(product_id)
    return StandardResponse(data={"deleted": True})


@router.post("/{product_id}/adjust-stock", response_model=StandardResponse[ProductOut])
async def adjust_stock(
    product_id: str,
    data: StockAdjustRequest,
    background_tasks: BackgroundTasks,
    svc: ProductService = Depends(_svc),
):
    pending: list[tuple] = []

    async def collect(store_id: str, event_type: str, payload: dict) -> None:
        pending.append((store_id, event_type, payload))

    product = await svc.adjust_stock(product_id, data, broadcast_fn=collect)
    for args in pending:
        background_tasks.add_task(manager.broadcast, *args)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.get("/{product_id}/movements", response_model=StandardResponse[list[StockMovementOut]])
async def get_movements(
    product_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(StockMovement)
        .where(StockMovement.product_id == product_id, StockMovement.store_id == store_id)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
    )
    movements = result.scalars().all()
    return StandardResponse(data=[
        StockMovementOut(
            id=m.id,
            product_id=m.product_id,
            store_id=m.store_id,
            quantity_change=m.quantity_change,
            reason=m.reason.value,
            reference_id=m.reference_id,
            user_id=m.user_id,
            created_at=m.created_at.isoformat(),
        )
        for m in movements
    ])
