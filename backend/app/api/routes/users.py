from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentAuth, require_csrf
from app.db.session import get_db
from app.schemas.auth import UserResponse
from app.schemas.user import UserUpdate


router = APIRouter(prefix="/users", tags=["users"])


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    auth: CurrentAuth = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if "display_name" in payload.model_fields_set:
        auth.user.display_name = payload.display_name
    if payload.locale is not None:
        auth.user.locale = payload.locale
    await db.commit()
    return UserResponse(
        id=auth.user.id,
        email=auth.user.email,
        display_name=auth.user.display_name,
        locale=auth.user.locale,
        role=auth.user.role,
        email_verified=auth.user.email_verified_at is not None,
    )
