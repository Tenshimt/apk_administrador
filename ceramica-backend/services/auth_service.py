import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.store import Store
from models.user import RefreshToken, User, UserRole
from schemas.auth import LoginRequest, LoginResponse, RegisterStoreRequest, TokenData

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {
            "sub": user.id,
            "store_id": user.store_id,
            "role": user.role.value,
            "email": user.email,
            "exp": expire,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register_store(self, data: RegisterStoreRequest) -> dict:
        # Check slug uniqueness
        result = await self.db.execute(select(Store).where(Store.slug == data.store_slug))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Store slug already taken")

        store = Store(
            name=data.store_name,
            slug=data.store_slug,
            owner_email=data.owner_email,
            currency_code=data.currency_code,
            timezone=data.timezone,
        )
        self.db.add(store)
        await self.db.flush()

        owner = User(
            store_id=store.id,
            email=data.owner_email,
            hashed_password=_hash_password(data.owner_password),
            full_name=data.owner_full_name,
            role=UserRole.owner,
        )
        self.db.add(owner)
        await self.db.flush()

        return {"store_id": store.id, "user_id": owner.id, "slug": store.slug}

    async def login(self, data: LoginRequest) -> LoginResponse:
        # Resolve store
        result = await self.db.execute(
            select(Store).where(Store.slug == data.store_slug, Store.is_active.is_(True))
        )
        store = result.scalar_one_or_none()
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")

        # Resolve user
        result = await self.db.execute(
            select(User).where(
                User.email == data.email,
                User.store_id == store.id,
                User.is_active.is_(True),
            )
        )
        user = result.scalar_one_or_none()
        if not user or not _verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        access_token = _create_access_token(user)
        raw_refresh = str(uuid.uuid4())
        refresh_record = RefreshToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=_hash_refresh_token(raw_refresh),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.add(refresh_record)

        return LoginResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            store_id=store.id,
            user_id=user.id,
            role=user.role.value,
        )

    async def refresh(self, raw_token: str) -> LoginResponse:
        token_hash = _hash_refresh_token(raw_token)
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
            )
        )
        record = result.scalar_one_or_none()
        if not record or record.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        # Rotate token
        record.revoked = True
        result = await self.db.execute(select(User).where(User.id == record.user_id))
        user = result.scalar_one()

        access_token = _create_access_token(user)
        raw_new = str(uuid.uuid4())
        new_record = RefreshToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=_hash_refresh_token(raw_new),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.add(new_record)

        return LoginResponse(
            access_token=access_token,
            refresh_token=raw_new,
            store_id=user.store_id,
            user_id=user.id,
            role=user.role.value,
        )

    async def logout(self, raw_token: str) -> None:
        token_hash = _hash_refresh_token(raw_token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        if record:
            record.revoked = True
