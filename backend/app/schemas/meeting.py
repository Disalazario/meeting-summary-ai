from datetime import datetime
from pydantic import BaseModel


class MeetingResponse(BaseModel):
    id: int
    title: str
    date: datetime | None
    status: str
    error_message: str | None = None
    processing_progress: int | None = None
    processing_eta_seconds: int | None = None
    duration_seconds: float | None = None
    source: str = "upload"
    meeting_url: str | None = None
    owner_id: int
    owner_name: str | None = None       # display_name владельца — для UI
    participated: bool = False          # говорил ли запрашивающий в этой встрече
    is_owner: bool = False              # владелец ли он
    created_at: datetime

    model_config = {"from_attributes": True}


class MeetingListItem(BaseModel):
    id: int
    title: str
    date: datetime | None
    status: str
    duration_seconds: float | None = None
    source: str = "upload"
    meeting_url: str | None = None
    owner_name: str | None = None
    participated: bool = False
    is_owner: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
