"""
Background scheduler for daily portfolio inference (IST market open).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from src.settings import (
    MARKET_TIMEZONE,
    PORTFOLIO_SCHEDULER_ENABLED,
    PORTFOLIO_SCHEDULER_HOUR,
    PORTFOLIO_SCHEDULER_MINUTE,
)

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_portfolio_scheduler() -> BackgroundScheduler | None:
    """Start cron job Mon–Fri at configured IST time; no-op if disabled."""
    global _scheduler
    if not PORTFOLIO_SCHEDULER_ENABLED:
        logger.info("Portfolio scheduler disabled (PORTFOLIO_SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    def _run_with_guard():
        from datetime import datetime
        from src.database.supabase_client import DhanNitiDatabase
        from src.services.portfolio_persistence import run_daily_portfolio_recommend
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            db = DhanNitiDatabase()
            report = db.get_latest_report()
            if report and report.get("date") == today:
                logger.info("Today's report already exists — skipping scheduler run")
                return
            run_daily_portfolio_recommend()
        except Exception as e:
            logger.error("Scheduler guard failed: %s", e)
            run_daily_portfolio_recommend()

    tz = ZoneInfo(MARKET_TIMEZONE)
    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        _run_with_guard,
        CronTrigger(
            hour=PORTFOLIO_SCHEDULER_HOUR,
            minute=PORTFOLIO_SCHEDULER_MINUTE,
            day_of_week="mon-fri",
            timezone=tz,
        ),
        id="daily_portfolio_recommend",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "Portfolio scheduler started: %02d:%02d %s Mon–Fri",
        PORTFOLIO_SCHEDULER_HOUR,
        PORTFOLIO_SCHEDULER_MINUTE,
        MARKET_TIMEZONE,
    )
    return _scheduler


def stop_portfolio_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Portfolio scheduler stopped")
