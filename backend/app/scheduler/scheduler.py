"""Scheduler définitif (spec.md § 4.7) — déclencheur découplé unique, sur lequel le
polling SuperPDP viendra se brancher au lot 6 (§ 4.1)."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db.session import SessionLocal
from app.services import retry_scheduler_service

_scheduler: BackgroundScheduler | None = None


def _run_send_cycle_job() -> None:
    db = SessionLocal()
    try:
        retry_scheduler_service.run_send_cycle(db)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_send_cycle_job,
        "interval",
        minutes=settings.retry_interval_minutes,
        id="mail-send-retry-cycle",
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
