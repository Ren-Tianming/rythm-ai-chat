from fastapi import APIRouter

from app.api.routes import auth, conversations, documents, health, models, users


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(models.router)
api_router.include_router(conversations.router)
api_router.include_router(health.router)

api_router.include_router(documents.router)
