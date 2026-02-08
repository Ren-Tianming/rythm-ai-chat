from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.llm import llm_service

router = APIRouter()

class ChatRequest(BaseModel):
    prompt: str
    history: list = []

@router.post("/chat")
def chat(req: ChatRequest):
    try:
        reply = llm_service.chat(req.prompt, req.history)
        return {
            "status": "success",
            "reply": reply
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
