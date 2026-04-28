from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user
from dependencies.store import get_store_id
from models.user import User
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.sale import PaymentCreate, PaymentOut, SaleCreate, SaleOut, SaleStatusUpdate
from services.sale_service import SaleService
from websocket_manager import manager

router = APIRouter(prefix="/sales", tags=["sales"])


def _svc(
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    user: User = Depends(get_current_user),
) -> SaleService:
    return SaleService(db, store_id, user)


@router.get("", response_model=PaginatedResponse[SaleOut])
async def list_sales(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: SaleService = Depends(_svc),
):
    sales, total = await svc.list_sales(limit=limit, offset=offset)
    return PaginatedResponse(
        data=[SaleOut.model_validate(s) for s in sales],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.post("", response_model=StandardResponse[SaleOut], status_code=201)
async def create_sale(data: SaleCreate, svc: SaleService = Depends(_svc)):
    sale = await svc.create(data, broadcast=manager.broadcast)
    return StandardResponse(data=SaleOut.model_validate(sale))


@router.get("/{sale_id}", response_model=StandardResponse[SaleOut])
async def get_sale(sale_id: str, svc: SaleService = Depends(_svc)):
    sale = await svc.get_or_404(sale_id)
    return StandardResponse(data=SaleOut.model_validate(sale))


@router.patch("/{sale_id}/status", response_model=StandardResponse[SaleOut])
async def update_status(
    sale_id: str, data: SaleStatusUpdate, svc: SaleService = Depends(_svc)
):
    sale = await svc.update_status(sale_id, data)
    return StandardResponse(data=SaleOut.model_validate(sale))


@router.post("/{sale_id}/payment", response_model=StandardResponse[SaleOut])
async def add_payment(
    sale_id: str, data: PaymentCreate, svc: SaleService = Depends(_svc)
):
    sale = await svc.add_payment(sale_id, data, broadcast=manager.broadcast)
    return StandardResponse(data=SaleOut.model_validate(sale))
