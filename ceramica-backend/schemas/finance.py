from datetime import datetime

from models.finance import ExpenseCategory
from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    category: ExpenseCategory
    amount_cents: int = Field(..., gt=0)
    notes: str | None = None
    client_generated_id: str | None = None


class ExpenseOut(BaseModel):
    id: str
    store_id: str
    description: str
    category: ExpenseCategory
    amount_cents: int
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardOut(BaseModel):
    period_label: str
    revenue_cents: int
    expenses_cents: int
    profit_cents: int
    sales_count: int
    pending_debt_cents: int
    low_stock_count: int
    accounts_receivable_cents: int = 0
    accounts_payable_cents: int = 0
    top_products: list[dict] = []


class CashflowOut(BaseModel):
    from_date: datetime
    to_date: datetime
    revenue_cents: int
    expenses_cents: int
    net_cents: int
    by_day: list[dict] = []


class ProfitLossOut(BaseModel):
    from_date: datetime
    to_date: datetime
    revenue_cents: int
    cogs_cents: int
    gross_profit_cents: int
    expenses_cents: int
    net_profit_cents: int
