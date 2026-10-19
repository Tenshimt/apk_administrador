from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies.auth import get_current_user, require_roles
from dependencies.store import get_store_id
from models.user import User, UserRole
from schemas.common import PaginatedResponse, PaginationMeta, StandardResponse
from schemas.finance import CashflowOut, DashboardOut, ExpenseCreate, ExpenseOut, ProfitLossOut
from services.finance_service import FinanceService

router = APIRouter(prefix="/finance", tags=["finance"])

_privileged = Depends(require_roles(UserRole.owner, UserRole.admin))


def _svc(
    db: AsyncSession = Depends(get_db),
    store_id: str = Depends(get_store_id),
    user: User = Depends(get_current_user),
) -> FinanceService:
    return FinanceService(db, store_id, user)


@router.get("/dashboard", response_model=StandardResponse[DashboardOut])
async def dashboard(
    period_days: int = Query(30, ge=1, le=365),
    svc: FinanceService = Depends(_svc),
):
    data = await svc.get_dashboard(period_days)
    return StandardResponse(data=DashboardOut(**data))


@router.post("/expense", response_model=StandardResponse[ExpenseOut], status_code=201)
async def create_expense(data: ExpenseCreate, _: User = _privileged, svc: FinanceService = Depends(_svc)):
    expense = await svc.create_expense(data)
    return StandardResponse(data=ExpenseOut.model_validate(expense))


@router.get("/cashflow", response_model=StandardResponse[CashflowOut])
async def cashflow(
    from_date: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=30)),
    to_date: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    svc: FinanceService = Depends(_svc),
):
    data = await svc.get_cashflow(from_date, to_date)
    return StandardResponse(data=CashflowOut(**data))


@router.get("/reports/profit-loss", response_model=StandardResponse[ProfitLossOut], dependencies=[_privileged])
async def profit_loss(
    from_date: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=30)),
    to_date: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    svc: FinanceService = Depends(_svc),
):
    data = await svc.get_profit_loss(from_date, to_date)
    return StandardResponse(data=ProfitLossOut(**data))


@router.get("/reports/sales", response_model=StandardResponse[dict])
async def sales_report(
    from_date: datetime = Query(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=30)),
    to_date: datetime = Query(default_factory=lambda: datetime.now(timezone.utc)),
    svc: FinanceService = Depends(_svc),
):
    data = await svc.get_cashflow(from_date, to_date)
    return StandardResponse(data=data, meta={"report_type": "sales"})


@router.get("/reports/inventory-valuation", response_model=StandardResponse[dict])
async def inventory_valuation(svc: FinanceService = Depends(_svc)):
    data = await svc.inventory_valuation()
    return StandardResponse(data=data)


@router.get("/expenses", response_model=PaginatedResponse[ExpenseOut])
async def list_expenses(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    svc: FinanceService = Depends(_svc),
):
    expenses, total = await svc.list_expenses(limit=limit, offset=offset)
    return PaginatedResponse(
        data=[ExpenseOut.model_validate(e) for e in expenses],
        meta=PaginationMeta(total=total, limit=limit, offset=offset, has_more=offset + limit < total),
    )
