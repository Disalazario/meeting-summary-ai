from pydantic import BaseModel


class SummaryResponse(BaseModel):
    id: int
    summary_text: str
    brief: str
    key_decisions: list[str] | None = None
    topics: list[str] | None = None

    model_config = {"from_attributes": True}
