from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.client import Client
from models.finance import Expense
from models.product import Product
from models.sale import Payment, Sale, SaleStatus
from models.user import User
from schemas.finance import ExpenseCreate

settings = get_settings()


class FinanceService:
    def __init__(self, db: AsyncSession, store_id: str, current_user: User | None = None) -> None:
        self.db = db
        self.store_id = store_id
        self.user = current_user

    async def get_dashboard(self, period_days: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        since = now - timedelta(days=period_days)

        # Revenue: sum of payments in period
        revenue_q = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.store_id == self.store_id, Payment.created_at >= since
        )
        revenue = (await self.db.execute(revenue_q)).scalar_one()

        # Expenses in period
        expenses_q = select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
            Expense.store_id == self.store_id,
            Expense.is_active.is_(True),
            Expense.created_at >= since,
        )
        expenses = (await self.db.execute(expenses_q)).scalar_one()

        # Sales count
        sales_q = select(func.count()).where(
            Sale.store_id == self.store_id,
            Sale.is_active.is_(True),
            Sale.created_at >= since,
        )
        sales_count = (await self.db.execute(sales_q)).scalar_one()

        # Pending debt
        debt_q = select(func.coalesce(func.sum(Client.debt_cents), 0)).where(
            Client.store_id == self.store_id, Client.is_active.is_(True)
        )
        pending_debt = (await self.db.execute(debt_q)).scalar_one()

        # Low stock count
        low_stock_q = select(func.count()).where(
            Product.store_id == self.store_id,
            Product.is_active.is_(True),
            Product.stock_quantity <= Product.low_stock_threshold,
        )
        low_stock_count = (await self.db.execute(low_stock_q)).scalar_one()

        return {
            "period_label": f"Last {period_days} days",
            "revenue_cents": revenue,
            "expenses_cents": expenses,
            "profit_cents": revenue - expenses,
            "sales_count": sales_count,
            "pending_debt_cents": pending_debt,
            "low_stock_count": low_stock_count,
            "top_products": [],  # Extended via background task
        }

    async def create_expense(self, data: ExpenseCreate) -> Expense:
        # Idempotency
        if data.client_generated_id:
            result = await self.db.execute(
                select(Expense).where(
                    Expense.client_generated_id == data.client_generated_id,
                    Expense.store_id == self.store_id,
                )
            )
            if existing := result.scalar_one_or_none():
                return existing

        expense = Expense(
            **data.model_dump(),
            store_id=self.store_id,
            recorded_by_id=self.user.id if self.user else None,
        )
        self.db.add(expense)
        await self.db.flush()
        return expense

    async def get_cashflow(self, from_date: datetime, to_date: datetime) -> dict:
        revenue_q = select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.store_id == self.store_id,
            Payment.created_at >= from_date,
            Payment.created_at <= to_date,
        )
        revenue = (await self.db.execute(revenue_q)).scalar_one()

        expenses_q = select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
            Expense.store_id == self.store_id,
            Expense.is_active.is_(True),
            Expense.created_at >= from_date,
            Expense.created_at <= to_date,
        )
        expenses = (await self.db.execute(expenses_q)).scalar_one()

        return {
            "from_date": from_date,
            "to_date": to_date,
            "revenue_cents": revenue,
            "expenses_cents": expenses,
            "net_cents": revenue - expenses,
            "by_day": [],
        }

    async def list_expenses(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[Expense], int]:
        q = (
            select(Expense)
            .where(Expense.store_id == self.store_id, Expense.is_active.is_(True))
            .order_by(Expense.created_at.desc())
        )
        from sqlalchemy import func as f

        total = (await self.db.execute(select(f.count()).select_from(q.subquery()))).scalar_one()
        expenses = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(expenses), total

    async def inventory_valuation(self) -> dict:
        result = await self.db.execute(
            select(
                func.count(Product.id),
                func.coalesce(func.sum(Product.stock_quantity * Product.cost_cents), 0),
                func.coalesce(func.sum(Product.stock_quantity * Product.price_cents), 0),
            ).where(Product.store_id == self.store_id, Product.is_active.is_(True))
        )
        row = result.one()
        return {
            "product_count": row[0],
            "cost_value_cents": row[1],
            "retail_value_cents": row[2],
            "potential_margin_cents": row[2] - row[1],
        }
