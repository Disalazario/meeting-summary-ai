from datetime import datetime

from sqlalchemy import Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    key_decisions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    topics: Mapped[str | None] = mapped_column(String, nullable=True, default=None)  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="summary")
