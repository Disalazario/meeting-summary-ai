"""
Планировщик встреч через APScheduler.

Два режима:
- Одноразовая встреча — DateTrigger, бот запускается за 1 минуту до начала.
- Еженедельная (рекуррентная) — CronTrigger по дню недели и времени, в
  указанной таймзоне (по умолчанию Europe/Moscow). Job переживает любое
  число срабатываний — пересоздаётся при рестарте backend через recovery
  в lifespan.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


# 0=Mon … 6=Sun для совместимости с Python's datetime.weekday()
WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _job_id(scheduled_meeting_id: int) -> str:
    return f"meeting_{scheduled_meeting_id}"


class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={"coalesce": True, "max_instances": 1}
        )

    def start(self):
        self.scheduler.start()
        logger.info("APScheduler запущен")

    def shutdown(self):
        self.scheduler.shutdown()
        logger.info("APScheduler остановлен")

    def schedule_meeting(self, scheduled_meeting_id: int,
                         start_time: datetime,
                         callback) -> str:
        """Одноразовый job: бот запускается за 1 минуту до start_time."""
        run_time = start_time - timedelta(minutes=1)

        if run_time <= datetime.now():
            run_time = datetime.now() + timedelta(seconds=5)

        job = self.scheduler.add_job(
            callback,
            trigger="date",
            run_date=run_time,
            args=[scheduled_meeting_id],
            id=_job_id(scheduled_meeting_id),
            replace_existing=True,
        )
        logger.info(f"Встреча {scheduled_meeting_id} запланирована на {run_time}")
        return job.id

    def schedule_recurring_weekly(
        self, scheduled_meeting_id: int,
        day_of_week: int,   # 0=Mon … 6=Sun
        time_str: str,      # "HH:MM"
        tz_name: str,       # e.g. "Europe/Moscow"
        callback,
    ) -> str:
        """Еженедельный CronTrigger в указанной таймзоне.

        Бот стартует за 1 минуту до времени встречи — поэтому из time_str
        вычитаем 1 минуту перед формированием cron.
        """
        if not 0 <= day_of_week <= 6:
            raise ValueError(f"day_of_week вне диапазона 0..6: {day_of_week}")
        try:
            hh, mm = time_str.split(":")
            hour, minute = int(hh), int(mm)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Неверный формат времени '{time_str}', нужно 'HH:MM': {e}")
        try:
            tz = ZoneInfo(tz_name)
        except Exception as e:
            raise ValueError(f"Неизвестная таймзона '{tz_name}': {e}")

        # Запуск бота за 1 минуту до начала.
        run_hour, run_minute = hour, minute - 1
        if run_minute < 0:
            run_minute += 60
            run_hour -= 1
            if run_hour < 0:
                run_hour += 24
                # переход на предыдущий день недели
                day_of_week = (day_of_week - 1) % 7

        trigger = CronTrigger(
            day_of_week=WEEKDAY_NAMES[day_of_week],
            hour=run_hour, minute=run_minute,
            timezone=tz,
        )

        job = self.scheduler.add_job(
            callback,
            trigger=trigger,
            args=[scheduled_meeting_id],
            id=_job_id(scheduled_meeting_id),
            replace_existing=True,
        )
        logger.info(
            f"Встреча {scheduled_meeting_id} запланирована ЕЖЕНЕДЕЛЬНО: "
            f"{WEEKDAY_NAMES[day_of_week]} {run_hour:02d}:{run_minute:02d} ({tz_name}). "
            f"Следующий запуск: {job.next_run_time}"
        )
        return job.id

    def cancel_meeting(self, scheduled_meeting_id: int) -> bool:
        """Снять job (как разовый, так и рекуррентный)."""
        try:
            self.scheduler.remove_job(_job_id(scheduled_meeting_id))
            logger.info(f"Встреча {scheduled_meeting_id} отменена")
            return True
        except Exception:
            logger.warning(f"Job {_job_id(scheduled_meeting_id)} не найден для отмены")
            return False

    def get_next_run(self, scheduled_meeting_id: int) -> datetime | None:
        """Время следующего срабатывания (None если job нет)."""
        try:
            job = self.scheduler.get_job(_job_id(scheduled_meeting_id))
        except Exception:
            return None
        return job.next_run_time if job else None

    def get_scheduled_jobs(self) -> list:
        """Список запланированных задач."""
        return [
            {
                "id": job.id,
                "run_date": str(job.next_run_time),
                "name": job.name,
            }
            for job in self.scheduler.get_jobs()
        ]
