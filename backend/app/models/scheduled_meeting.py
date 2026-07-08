from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean

from app.database import Base


class ScheduledMeeting(Base):
    """Запланированная встреча — одноразовая или рекуррентная.

    Тип задаёт `recurrence`:
    - 'none' — одноразовая, время в `scheduled_at`. Статус идёт по циклу
      pending → starting → active → completed (или cancelled / error).
    - 'weekly' — еженедельная по `recurrence_day` (0=Пн … 6=Вс) в
      `recurrence_time` ("HH:MM") по таймзоне `timezone` (default
      Europe/Moscow). `scheduled_at` для weekly не используется (NULL).
      Статус остаётся 'pending' постоянно — каждое срабатывание создаёт
      отдельный Meeting, но саму запись расписания не закрывает.
      Чтобы приостановить — переключить `is_active=False` (job отменяется).
    """
    __tablename__ = "scheduled_meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)

    # one-off: точная дата и время. Для weekly остаётся NULL.
    scheduled_at = Column(DateTime, nullable=True)

    # Ссылка на УЖЕ СОЗДАННУЮ встречу в Телемост, к которой бот подключится.
    meeting_url = Column(String, nullable=True)

    # Рекуррентность.
    recurrence = Column(String, nullable=False, default="none")  # 'none' | 'weekly'
    recurrence_day = Column(Integer, nullable=True)   # 0=Mon … 6=Sun
    recurrence_time = Column(String, nullable=True)   # "HH:MM"
    timezone = Column(String, nullable=False, default="Europe/Moscow")

    # Активен ли расписание (можно «приостановить» рекуррентный без удаления).
    is_active = Column(Boolean, nullable=False, default=True)

    # one-off lifecycle: pending | starting | active | completed | cancelled | error.
    # weekly: всегда 'pending' (если is_active), либо 'cancelled' если паузнули/удалили.
    status = Column(String, default="pending")
    error_message = Column(Text, nullable=True)

    telegram_group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=True)
    # Для one-off — ссылка на созданный Meeting (один). Для weekly не используется
    # (каждое срабатывание создаёт собственный Meeting, искать через Meetings list).
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
