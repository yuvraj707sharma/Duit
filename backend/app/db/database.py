"""SQLAlchemy Database Engine and Session Dependency."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from backend.app.config import settings

Base = declarative_base()

db_url = settings.DATABASE_URL
has_asyncpg = False
try:
    import asyncpg
    has_asyncpg = True
except ImportError:
    has_asyncpg = False

if "postgresql" in db_url and not has_asyncpg:
    # Graceful fallback to in-memory async SQLite when asyncpg driver is not installed on host
    db_url = "sqlite+aiosqlite:///:memory:"

if "sqlite" in db_url:
    engine = create_async_engine(db_url, echo=False)
else:
    engine = create_async_engine(
        db_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing database sessions scoped to a single request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
