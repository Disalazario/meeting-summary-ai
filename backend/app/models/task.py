from sqlalchemy import Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[int] = mapped_column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # «зачем» — короткое объяснение
    assignee: Mapped[str | None] = mapped_column(String, nullable=True)
    deadline: Mapped[str | None] = mapped_column(String, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    # PlanFix integration
    planfix_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    planfix_sent_at: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    meeting = relationship("Meeting", back_populates="tasks")
