from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_auth
from app.db.models import ModelProfile
from app.db.session import get_db
from app.schemas.chat import ModelProfileResponse


router = APIRouter(prefix="/model-profiles", tags=["models"], dependencies=[Depends(get_current_auth)])


@router.get("", response_model=list[ModelProfileResponse])
async def list_models(db: AsyncSession = Depends(get_db)) -> list[ModelProfileResponse]:
    models = (
        await db.scalars(
            select(ModelProfile).where(ModelProfile.enabled.is_(True)).order_by(ModelProfile.display_name)
        )
    ).all()
    return [
        ModelProfileResponse(
            id=item.id,
            slug=item.slug,
            provider=item.provider,
            display_name=item.display_name,
            description_key=item.description_key,
            is_default=item.is_default,
            max_output_tokens=item.max_output_tokens,
        )
        for item in models
    ]
