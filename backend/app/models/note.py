from datetime import datetime

from sqlalchemy import Integer, ForeignKey, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MeetingNote(Base):
    """Личные заметки пользователя по конкретной встрече.

    Каждый участник ведёт свои заметки. После генерации саммари пайплайн
    делает доп. LLM-проход для автора встречи (owner): берёт его заметки
    и обогащает контекстом из транскрипта. Результат — в enriched_content.
    """
    __tablename__ = "meeting_notes"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_notes_meeting_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enriched_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User")
