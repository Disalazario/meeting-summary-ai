from datetime import datetime
from pydantic import BaseModel


class MeetingNoteAuthor(BaseModel):
    id: int
    display_name: str


class MeetingNoteResponse(BaseModel):
    id: int
    meeting_id: int
    content: str
    enriched_content: str | None = None
    enriched_at: datetime | None = None
    updated_at: datetime
    author: MeetingNoteAuthor

    model_config = {"from_attributes": True}


class MyMeetingNoteResponse(BaseModel):
    """Заметка текущего пользователя по встрече (без блока author — это всегда он сам)."""
    content: str
    enriched_content: str | None = None
    enriched_at: datetime | None = None
    updated_at: datetime | None = None


class MeetingNoteUpdateRequest(BaseModel):
    content: str
