from pydantic import BaseModel
from typing import List

class ChatRequest(BaseModel):
    prompt: str
    history: List[str] = []

class ChatResponse(BaseModel):
    reply: str
    status: str
