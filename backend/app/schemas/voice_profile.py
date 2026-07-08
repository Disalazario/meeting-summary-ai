from datetime import datetime

from pydantic import BaseModel


class VoiceProfileStatus(BaseModel):
    enrolled: bool
    sample_count: int | None = None
    updated_at: datetime | None = None
