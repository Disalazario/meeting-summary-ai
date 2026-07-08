from pydantic import BaseModel


class TranscriptSegmentResponse(BaseModel):
    id: int
    speaker_label: str
    text: str
    start_time: float
    end_time: float
    confidence: float | None = None

    model_config = {"from_attributes": True}


class SpeakerRenameRequest(BaseModel):
    speakers: dict[str, str]  # {"SPEAKER_00": "Иван"}
