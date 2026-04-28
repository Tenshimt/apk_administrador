from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

settings = get_settings()

# SQLite needs check_same_thread=False via connect_args; PostgreSQL needs pool tuning
connect_args = {"check_same_thread": False} if settings.use_sqlite else {}
pool_kwargs = (
    {}
    if settings.use_sqlite
    else {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}
)

engine = create_async_engine(
    settings.database_url,
    connect_args=connect_args,
    **pool_kwargs,
    echo=not settings.is_production,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Used in development / tests — production uses Alembic migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
