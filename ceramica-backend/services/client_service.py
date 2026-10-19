from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from models.client import Client
from models.sale import Payment, Sale, SaleStatus
from models.user import User
from schemas.client import ClientCreate, ClientUpdate
from schemas.sale import PaymentCreate

settings = get_settings()


class ClientService:
    def __init__(self, db: AsyncSession, store_id: str, current_user: User | None = None) -> None:
        self.db = db
        self.store_id = store_id
        self.user = current_user

    async def list_clients(
        self,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
    ) -> tuple[list[Client], int]:
        q = select(Client).where(
            Client.store_id == self.store_id, Client.is_active.is_(True)
        )
        if search:
            q = q.where(
                Client.full_name.ilike(f"%{search}%") | Client.phone.ilike(f"%{search}%")
            )
        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()
        clients = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(clients), total

    async def get_or_404(self, client_id: str) -> Client:
        result = await self.db.execute(
            select(Client).where(
                Client.id == client_id,
                Client.store_id == self.store_id,
                Client.is_active.is_(True),
            )
        )
        client = result.scalar_one_or_none()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client

    async def create(self, data: ClientCreate) -> Client:
        if data.client_generated_id:
            result = await self.db.execute(
                select(Client).where(
                    Client.client_generated_id == data.client_generated_id,
                    Client.store_id == self.store_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        client = Client(**data.model_dump(), store_id=self.store_id)
        self.db.add(client)
        await self.db.flush()
        return client

    async def update(self, client_id: str, data: ClientUpdate) -> Client:
        client = await self.get_or_404(client_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(client, key, value)
        await self.db.flush()
        return client

    async def get_debt(self, client_id: str) -> dict:
        client = await self.get_or_404(client_id)
        result = await self.db.execute(
            select(Sale).where(
                Sale.client_id == client_id,
                Sale.store_id == self.store_id,
                Sale.status.in_([SaleStatus.partial, SaleStatus.pending]),
            )
        )
        pending_sales = result.scalars().all()
        return {
            "client_id": client.id,
            "full_name": client.full_name,
            "debt_cents": client.debt_cents,
            "pending_sales": [
                {
                    "sale_id": s.id,
                    "total_cents": s.total_cents,
                    "paid_cents": s.paid_cents,
                    "balance_cents": s.balance_cents,
                }
                for s in pending_sales
            ],
        }

    async def apply_fifo_payment(self, client_id: str, data: PaymentCreate) -> list[dict]:
        """Distribute a payment FIFO across all unpaid sales."""
        client = await self.get_or_404(client_id)
        result = await self.db.execute(
            select(Sale)
            .where(
                Sale.client_id == client_id,
                Sale.store_id == self.store_id,
                Sale.status.in_([SaleStatus.pending, SaleStatus.partial]),
            )
            .order_by(Sale.created_at.asc())
        )
        pending_sales = result.scalars().all()

        total_debt = sum(s.balance_cents for s in pending_sales)
        if data.amount_cents > total_debt:
            raise HTTPException(
                status_code=400,
                detail=f"Payment ({data.amount_cents}) exceeds total client debt ({total_debt})",
            )

        remaining = data.amount_cents
        applied = []

        for sale in pending_sales:
            if remaining <= 0:
                break
            apply_amount = min(remaining, sale.balance_cents)
            payment = Payment(
                sale_id=sale.id,
                store_id=self.store_id,
                amount_cents=apply_amount,
                method=data.method,
                reference=data.reference,
            )
            self.db.add(payment)
            sale.paid_cents += apply_amount
            client.debt_cents = max(0, client.debt_cents - apply_amount)
            remaining -= apply_amount

            if sale.paid_cents >= sale.total_cents:
                sale.status = SaleStatus.completed
            elif sale.paid_cents > 0:
                sale.status = SaleStatus.partial

            applied.append({"sale_id": sale.id, "amount_cents": apply_amount})

        await self.db.flush()
        return applied

    async def get_history(
        self, client_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[Sale], int]:
        await self.get_or_404(client_id)
        q = (
            select(Sale)
            .where(Sale.client_id == client_id, Sale.store_id == self.store_id)
            .options(selectinload(Sale.items), selectinload(Sale.payments))
            .order_by(Sale.created_at.desc())
        )
        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()
        sales = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(sales), total
