"""
APScheduler-based report scheduler.

Runs as a BackgroundScheduler (separate thread, no async required).
On startup: loads all active ReportSchedule rows from the DB and registers
a job for each one. Jobs are also added/removed when schedules are created
or deleted via the API.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Module-level scheduler singleton
scheduler = BackgroundScheduler(timezone="UTC")


# ── Public API ────────────────────────────────────────────────────────────────

def start(app=None) -> None:
    """Load active schedules from DB and start the scheduler."""
    _register_all_active_jobs()

    # Live-data sweep: refresh any connected dataset whose interval elapsed.
    # Runs every 5 minutes; each dataset's own interval gates the actual fetch.
    from app.services.data_refresh import refresh_due_datasets
    scheduler.add_job(
        refresh_due_datasets,
        trigger="interval",
        minutes=1,
        id="dataset_refresh_sweep",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # CH-18: daily retention purge — hard-delete accounts (rows + files)
    # whose soft-delete window (ADMIN_USER_RETENTION_DAYS) has expired.
    scheduler.add_job(
        _run_user_purge,
        trigger="cron",
        hour=3, minute=15,
        id="deleted_user_purge",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    if not scheduler.running:
        scheduler.start()
        print("[Scheduler] APScheduler started (incl. live-data sweep).")


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("[Scheduler] APScheduler stopped.")


def _run_user_purge() -> None:
    """CH-18 daily job wrapper — own DB session, logs the purge count."""
    from app.core.database import SessionLocal
    from app.api.v1.admin import purge_deleted_users
    db = SessionLocal()
    try:
        n = purge_deleted_users(db)
        if n:
            print(f"[Scheduler] Purged {n} account(s) past the retention window.")
    except Exception as exc:
        print(f"[Scheduler] User purge failed: {exc}")
    finally:
        db.close()


def add_schedule_job(schedule_id: int, frequency: str,
                     send_hour: int = 8, send_minute: int = 0,
                     day_of_week=None, day_of_month=None,
                     timezone: str = "UTC") -> None:
    """Register (or replace) the APScheduler job for a schedule."""
    trigger = _make_trigger(frequency, send_hour, send_minute, day_of_week, day_of_month, timezone)
    scheduler.add_job(
        _send_report_job,
        trigger=trigger,
        id=f"report_{schedule_id}",
        kwargs={"schedule_id": schedule_id},
        replace_existing=True,
        misfire_grace_time=3600,
    )


def add_schedule_job_from(sched) -> None:
    """Register the job from a ReportSchedule row."""
    add_schedule_job(
        sched.id, sched.frequency,
        send_hour=getattr(sched, "send_hour", 8) or 8,
        send_minute=getattr(sched, "send_minute", 0) or 0,
        day_of_week=getattr(sched, "day_of_week", None),
        day_of_month=getattr(sched, "day_of_month", None),
        timezone=getattr(sched, "timezone", "UTC") or "UTC",
    )


def remove_schedule_job(schedule_id: int) -> None:
    """Remove the APScheduler job for a schedule (if it exists)."""
    job_id = f"report_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def next_run_for(frequency: str, send_hour: int = 8, send_minute: int = 0,
                 day_of_week=None, day_of_month=None,
                 timezone: str = "UTC") -> Optional[datetime]:
    """Return the next fire time for a schedule configuration."""
    if frequency == "monthly":
        return _next_monthly_fire(day_of_month, send_hour, send_minute, timezone or "UTC")
    trigger = _make_trigger(frequency, send_hour, send_minute, day_of_week, day_of_month, timezone)
    return trigger.get_next_fire_time(None, datetime.now(trigger.timezone))


def next_run_from(sched) -> Optional[datetime]:
    """Next fire time computed from a ReportSchedule row."""
    return next_run_for(
        sched.frequency,
        send_hour=getattr(sched, "send_hour", 8) or 8,
        send_minute=getattr(sched, "send_minute", 0) or 0,
        day_of_week=getattr(sched, "day_of_week", None),
        day_of_month=getattr(sched, "day_of_month", None),
        timezone=getattr(sched, "timezone", "UTC") or "UTC",
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

_APS_DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _make_trigger(frequency: str, send_hour: int = 8, send_minute: int = 0,
                  day_of_week=None, day_of_month=None,
                  timezone: str = "UTC") -> CronTrigger:
    try:
        tz = timezone or "UTC"
        if frequency == "daily":
            return CronTrigger(hour=send_hour, minute=send_minute, timezone=tz)
        if frequency == "weekly":
            dow = _APS_DOW[day_of_week] if day_of_week is not None and 0 <= day_of_week <= 6 else "mon"
            return CronTrigger(day_of_week=dow, hour=send_hour, minute=send_minute, timezone=tz)
        # monthly — APScheduler's cron day-field can't express "day N, or the
        # month's last day if N doesn't exist" as a single trigger, so the job
        # fires every day at the target time and _send_report_job gates the
        # actual send with _is_monthly_send_day() (clamps to the last day).
        return CronTrigger(hour=send_hour, minute=send_minute, timezone=tz)
    except Exception:
        # Unknown timezone or bad values — fall back to safe defaults
        return CronTrigger(hour=8, minute=0, timezone="UTC")


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def _tz_now(tz: str = "UTC") -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz or "UTC"))
    except Exception:
        return datetime.utcnow()


def _effective_day(day_of_month, year: int, month: int) -> int:
    """Clamp a requested day-of-month (1-31) to the last real day of the given month."""
    target = day_of_month if day_of_month and 1 <= day_of_month <= 31 else 1
    return min(target, _days_in_month(year, month))


def _is_monthly_send_day(day_of_month, timezone: str = "UTC") -> bool:
    """True if today is the (clamped) target day for a monthly schedule."""
    now = _tz_now(timezone)
    return now.day == _effective_day(day_of_month, now.year, now.month)


def _next_monthly_fire(day_of_month, send_hour: int, send_minute: int,
                        timezone: str = "UTC") -> Optional[datetime]:
    """Next fire time for a monthly schedule, clamping to each month's last day."""
    now = _tz_now(timezone)
    year, month = now.year, now.month
    for _ in range(14):
        effective = _effective_day(day_of_month, year, month)
        candidate = datetime(year, month, effective, send_hour, send_minute, tzinfo=now.tzinfo)
        if candidate > now:
            return candidate
        month += 1
        if month > 12:
            month = 1
            year += 1
    return None


def _register_all_active_jobs() -> None:
    """Called once at startup — loads schedules from DB and adds jobs."""
    try:
        from app.core.database import SessionLocal
        from app.crud.schedule import get_all_active_schedules

        db = SessionLocal()
        try:
            schedules = get_all_active_schedules(db)
            for s in schedules:
                add_schedule_job_from(s)
            print(f"[Scheduler] Registered {len(schedules)} active report job(s).")
        finally:
            db.close()
    except Exception as exc:
        print(f"[Scheduler] Warning: could not load schedules at startup: {exc}")


def _send_report_job(schedule_id: int) -> None:
    """
    APScheduler job: generate a dashboard summary and email it.
    Opens its own DB session (runs in a background thread, not the request thread).
    """
    from app.core.database import SessionLocal
    from app.crud.schedule import get_all_active_schedules, update_run_status
    from app.services.insights.summary_generator import (
        generate_dashboard_summary, render_html_email, render_pdf_report,
    )
    from app.services.email.email_sender import send_report_email

    db = SessionLocal()
    try:
        from app.models.schedule import ReportSchedule
        sched = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
        if not sched or not sched.is_active:
            return

        # Monthly jobs fire daily at the target time — skip unless today is the
        # (last-day-clamped) target day for this month.
        if sched.frequency == "monthly" and not _is_monthly_send_day(
            sched.day_of_month, sched.timezone or "UTC"
        ):
            return

        dashboard = sched.dashboard

        # Live data: pull the latest from connected sources, then re-execute
        # every chart's query so the report reflects CURRENT data, not the
        # snapshot from when the chart was added.
        try:
            from app.services.data_refresh import refresh_dataset, refresh_dashboard_data
            from app.models.dataset import Dataset as DatasetModel
            import json as _json
            cfg = _json.loads(dashboard.config_json)
            ds_ids = {(c.get("dataset") or {}).get("id")
                      for c in cfg.get("charts", []) if (c.get("dataset") or {}).get("id")}
            for ds_id in ds_ids:
                ds = db.query(DatasetModel).filter(DatasetModel.id == ds_id).first()
                if ds and ds.source_type == "google_sheets" and ds.source_url:
                    refresh_dataset(db, ds)
            refresh_dashboard_data(db, dashboard)
            db.refresh(dashboard)
        except Exception as exc:
            print(f"[Scheduler] pre-report refresh failed (sending with stored data): {exc}")

        summary   = generate_dashboard_summary(dashboard)
        html_body = render_html_email(summary, sched.frequency)
        pdf_bytes = render_pdf_report(summary, sched.frequency)

        safe_name = dashboard.name.replace(" ", "_").replace("/", "-")[:40]
        pdf_filename = f"{safe_name}_report.pdf"

        subject = f"[{sched.frequency.capitalize()} Report] {dashboard.name}"
        ok = send_report_email(
            recipient=sched.recipient_email,
            subject=subject,
            html_body=html_body,
            pdf_bytes=pdf_bytes or None,
            pdf_filename=pdf_filename,
        )

        now = datetime.utcnow()
        next_fire = next_run_from(sched)
        update_run_status(
            db, schedule_id,
            next_run=next_fire,
            last_run=now,
            status="sent" if ok else "failed",
        )
        print(f"[Scheduler] Report {'sent' if ok else 'FAILED'} → {sched.recipient_email} (schedule #{schedule_id})")

    except Exception as exc:
        print(f"[Scheduler] Error in _send_report_job #{schedule_id}: {exc}")
        try:
            update_run_status(db, schedule_id, next_run=None, last_run=datetime.utcnow(), status="failed")
        except Exception:
            pass
    finally:
        db.close()
