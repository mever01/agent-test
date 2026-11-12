import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from alembic.config import Config
from alembic import command

from app.configs import settings

engine = create_async_engine(
    settings.db.async_url,
    pool_size=settings.db.pool_size,
    max_overflow=5,
    echo=settings.app.debug,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def _run_alembic_upgrade() -> None:
    """Синхронный запуск миграций Alembic до head."""
    project_root = Path(__file__).parents[2]
    ini_path = project_root / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    command.upgrade(alembic_cfg, "head")

async def init_db() -> None:
    """Применяет миграции Alembic до head в отдельном потоке executor."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_alembic_upgrade)
