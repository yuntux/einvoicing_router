"""Scheduler définitif (spec.md § 4.7) — déclencheur découplé unique, sur lequel se
branchent le cycle d'envoi/retry (§ 4.7, lot 5) et le polling SuperPDP (§ 4.1, lot 6)."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db.session import SessionLocal
from app.scheduler.polling_job import run_polling_cycle
from app.services import retry_scheduler_service, technical_log_purge_service

_scheduler: BackgroundScheduler | None = None


def _run_send_cycle_job() -> None:
    db = SessionLocal()
    try:
        retry_scheduler_service.run_send_cycle(db)
    finally:
        db.close()


def _run_polling_cycle_job() -> None:
    db = SessionLocal()
    try:
        run_polling_cycle(db)
    finally:
        db.close()


def _run_technical_log_purge_job() -> None:
    db = SessionLocal()
    try:
        technical_log_purge_service.purge_technical_logs(db)
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
    _scheduler.add_job(
        _run_polling_cycle_job,
        "interval",
        minutes=settings.polling_interval_minutes,
        id="superpdp-polling-cycle",
    )
    _scheduler.add_job(
        _run_technical_log_purge_job,
        "interval",
        hours=settings.technical_log_purge_interval_hours,
        id="technical-log-purge",
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
