from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user
from dependencies.store import get_store_id
from models.sale import Sale, SaleStatus
from models.user import User
from schemas.client import ClientCreate, ClientDebtOut, ClientOut, ClientUpdate
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.sale import PaymentCreate, SaleOut
from services.client_service import ClientService
from services.sale_service import SaleService
from websocket_manager import manager

router = APIRouter(prefix="/clients", tags=["clients"])


def _svc(
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    user: User = Depends(get_current_user),
) -> ClientService:
    return ClientService(db, store_id, user)


@router.get("", response_model=PaginatedResponse[ClientOut])
async def list_clients(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    svc: ClientService = Depends(_svc),
):
    clients, total = await svc.list_clients(limit=limit, offset=offset, search=search)
    return PaginatedResponse(
        data=[ClientOut.model_validate(c) for c in clients],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )


@router.post("", response_model=StandardResponse[ClientOut], status_code=201)
async def create_client(data: ClientCreate, svc: ClientService = Depends(_svc)):
    client = await svc.create(data)
    return StandardResponse(data=ClientOut.model_validate(client))


@router.get("/{client_id}", response_model=StandardResponse[ClientOut])
async def get_client(client_id: str, svc: ClientService = Depends(_svc)):
    client = await svc.get_or_404(client_id)
    return StandardResponse(data=ClientOut.model_validate(client))


@router.put("/{client_id}", response_model=StandardResponse[ClientOut])
async def update_client(
    client_id: str, data: ClientUpdate, svc: ClientService = Depends(_svc)
):
    client = await svc.update(client_id, data)
    return StandardResponse(data=ClientOut.model_validate(client))


@router.get("/{client_id}/debt", response_model=StandardResponse[ClientDebtOut])
async def get_client_debt(client_id: str, svc: ClientService = Depends(_svc)):
    debt_info = await svc.get_debt(client_id)
    return StandardResponse(data=ClientDebtOut(**debt_info))


@router.post("/{client_id}/payment", response_model=StandardResponse[dict])
async def client_payment(
    client_id: str,
    data: PaymentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    user: User = Depends(get_current_user),
    client_svc: ClientService = Depends(_svc),
):
    """Apply a payment to a client's oldest unpaid sale."""
    client = await client_svc.get_or_404(client_id)
    result = await db.execute(
        select(Sale)
        .where(
            Sale.client_id == client_id,
            Sale.store_id == store_id,
            Sale.status.in_([SaleStatus.pending, SaleStatus.partial]),
        )
        .order_by(Sale.created_at.asc())
        .limit(1)
    )
    sale = result.scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=400, detail="Client has no outstanding sales")

    pending: list[tuple] = []

    async def collect(s_id: str, event_type: str, payload: dict) -> None:
        pending.append((s_id, event_type, payload))

    sale_svc = SaleService(db, store_id, user)
    await sale_svc.add_payment(sale.id, data, broadcast=collect)
    for args in pending:
        background_tasks.add_task(manager.broadcast, *args)
    return StandardResponse(data={"message": "Payment applied", "sale_id": sale.id})


@router.get("/{client_id}/history", response_model=PaginatedResponse[SaleOut])
async def client_history(
    client_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: ClientService = Depends(_svc),
):
    sales, total = await svc.get_history(client_id, limit=limit, offset=offset)
    return PaginatedResponse(
        data=[SaleOut.model_validate(s) for s in sales],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )
