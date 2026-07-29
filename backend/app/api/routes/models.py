from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentAuth, get_current_auth
from app.core.config import Settings, get_settings
from app.db.models import ModelProfile
from app.db.session import get_db
from app.schemas.chat import ModelProfileResponse
from app.services.llm import configured_provider_names


router = APIRouter(prefix="/model-profiles", tags=["models"], dependencies=[Depends(get_current_auth)])


@router.get("", response_model=list[ModelProfileResponse])
async def list_models(
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[ModelProfileResponse]:
    configured = configured_provider_names(settings)
    models = (
        await db.scalars(
            select(ModelProfile)
            .where(
                ModelProfile.enabled.is_(True),
                ModelProfile.provider.in_(configured),
            )
            .order_by(ModelProfile.sort_order, ModelProfile.display_name)
        )
    ).all()
    return [
        ModelProfileResponse(
            id=item.id,
            slug=item.slug,
            provider=item.provider,
            display_name=item.display_name_i18n.get(auth.user.locale, item.display_name),
            description_key=item.description_key,
            is_default=item.is_default,
            max_output_tokens=item.max_output_tokens,
        )
        for item in models
    ]
