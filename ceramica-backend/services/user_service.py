from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User, UserRole
from schemas.user import UserCreate, UserUpdate

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, db: AsyncSession, store_id: str) -> None:
        self.db = db
        self.store_id = store_id

    async def list_users(self, limit: int = 20, offset: int = 0) -> tuple[list[User], int]:
        q = select(User).where(User.store_id == self.store_id)
        total = (await self.db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
        users = (await self.db.execute(q.offset(offset).limit(limit))).scalars().all()
        return list(users), total

    async def get_or_404(self, user_id: str) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.store_id == self.store_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    async def create(self, data: UserCreate) -> User:
        result = await self.db.execute(
            select(User).where(User.email == data.email, User.store_id == self.store_id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered in this store")

        user = User(
            email=data.email,
            hashed_password=_pwd.hash(data.password),
            full_name=data.full_name,
            role=data.role,
            store_id=self.store_id,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def update(self, user_id: str, data: UserUpdate) -> User:
        user = await self.get_or_404(user_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(user, key, value)
        await self.db.flush()
        return user
