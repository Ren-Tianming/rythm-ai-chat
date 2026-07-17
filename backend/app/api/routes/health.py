from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready"}
