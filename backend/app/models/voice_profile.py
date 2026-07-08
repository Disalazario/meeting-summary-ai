from datetime import datetime

from sqlalchemy import Integer, ForeignKey, DateTime, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True,
    )
    # Усреднённый embedding (ECAPA-TDNN, 192-dim float32) в виде bytes.
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    user = relationship("User", back_populates="voice_profile")
