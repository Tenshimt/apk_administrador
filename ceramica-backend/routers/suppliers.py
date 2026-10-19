from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user
from dependencies.store import get_store_id
from models.user import User
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.supplier import (
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderReceive,
    SupplierCreate,
    SupplierOut,
)
from services.supplier_service import SupplierService
from websocket_manager import manager

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _svc(
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    user: User = Depends(get_current_user),
) -> SupplierService:
    return SupplierService(db, store_id, user)


@router.get("", response_model=PaginatedResponse[SupplierOut])
async def list_suppliers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: SupplierService = Depends(_svc),
):
    suppliers, total = await svc.list_suppliers(limit=limit, offset=offset)
    return PaginatedResponse(
        data=[SupplierOut.model_validate(s) for s in suppliers],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.post("", response_model=StandardResponse[SupplierOut], status_code=201)
async def create_supplier(data: SupplierCreate, svc: SupplierService = Depends(_svc)):
    supplier = await svc.create_supplier(data)
    return StandardResponse(data=SupplierOut.model_validate(supplier))


@router.post("/purchase-orders", response_model=StandardResponse[PurchaseOrderOut], status_code=201)
async def create_purchase_order(data: PurchaseOrderCreate, svc: SupplierService = Depends(_svc)):
    order = await svc.create_purchase_order(data)
    return StandardResponse(data=PurchaseOrderOut.model_validate(order))


@router.get("/purchase-orders", response_model=PaginatedResponse[PurchaseOrderOut])
async def list_purchase_orders(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: SupplierService = Depends(_svc),
):
    orders, total = await svc.list_purchase_orders(limit=limit, offset=offset)
    return PaginatedResponse(
        data=[PurchaseOrderOut.model_validate(o) for o in orders],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.patch(
    "/purchase-orders/{order_id}/receive", response_model=StandardResponse[PurchaseOrderOut]
)
async def receive_order(
    order_id: str,
    data: PurchaseOrderReceive,
    background_tasks: BackgroundTasks,
    svc: SupplierService = Depends(_svc),
):
    pending: list[tuple] = []

    async def collect(store_id: str, event_type: str, payload: dict) -> None:
        pending.append((store_id, event_type, payload))

    order = await svc.receive_order(order_id, data, broadcast=collect)
    for args in pending:
        background_tasks.add_task(manager.broadcast, *args)
    return StandardResponse(data=PurchaseOrderOut.model_validate(order))
