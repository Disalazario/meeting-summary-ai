from datetime import datetime
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    response: str
