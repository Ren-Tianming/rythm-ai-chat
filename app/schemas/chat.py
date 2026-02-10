from pydantic import BaseModel
from typing import List, Literal

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    prompt: str
    history: List[Message] = []

class ChatResponse(BaseModel):
    status: str
    reply: str
