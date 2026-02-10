from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import llm_service

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        reply = llm_service.chat(req.prompt, req.history)
        return ChatResponse(status="success", reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
