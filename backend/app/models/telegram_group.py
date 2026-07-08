from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.database import Base


class TelegramGroup(Base):
    __tablename__ = "telegram_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    chat_id = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
