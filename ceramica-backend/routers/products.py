from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user
from dependencies.store import get_store_id
from models.user import User
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.product import ProductCreate, ProductOut, ProductUpdate, StockAdjustRequest
from services.product_service import ProductService
from websocket_manager import manager

router = APIRouter(prefix="/products", tags=["products"])


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


@router.post("", response_model=StandardResponse[ProductOut], status_code=201)
async def create_product(data: ProductCreate, svc: ProductService = Depends(_svc)):
    product = await svc.create(data)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.get("/{product_id}", response_model=StandardResponse[ProductOut])
async def get_product(product_id: str, svc: ProductService = Depends(_svc)):
    product = await svc.get_or_404(product_id)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.put("/{product_id}", response_model=StandardResponse[ProductOut])
async def update_product(
    product_id: str, data: ProductUpdate, svc: ProductService = Depends(_svc)
):
    product = await svc.update(product_id, data)
    return StandardResponse(data=ProductOut.model_validate(product))


@router.delete("/{product_id}", response_model=StandardResponse[dict])
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
