from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Conversation LLM API")

app.include_router(router)
