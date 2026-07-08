from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="uploaded")
    # statuses: uploaded, processing, transcribing, diarizing, summarizing, done, error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_eta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_path: Mapped[str] = mapped_column(String, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, default="upload")  # upload | bot
    meeting_url: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String, nullable=True)
    participant_names: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of names from Telemost
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="meetings")
    transcript_segments = relationship(
        "TranscriptSegment", back_populates="meeting", cascade="all, delete-orphan"
    )
    summary = relationship(
        "Summary", back_populates="meeting", uselist=False, cascade="all, delete-orphan"
    )
    tasks = relationship("Task", back_populates="meeting", cascade="all, delete-orphan")
    chat_messages = relationship(
        "ChatMessage", back_populates="meeting", cascade="all, delete-orphan"
    )
