from fastapi import APIRouter, Depends
from sqlalchemy import text
from app.api.dependencies import get_db, require_role
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/drafts", tags=["Drafts"])

@router.get(
    "/",
    dependencies=[Depends(require_role(["manager", "admin"]))],
)
async def list_drafts(session: AsyncSession = Depends(get_db)):
    """Просмотр созданных агентом черновиков."""
    query = """
        SELECT id, thread_id, recipient, subject, text, created_at
        FROM drafts
        ORDER BY created_at DESC
        LIMIT 50;
    """
    result = await session.execute(text(query))
    rows = result.mappings().all()
    return [dict(row) for row in rows]

