"""CRUD operations for ReportSchedule."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.schedule import ReportSchedule
from app.schemas.schedule import ScheduleCreate


def create_schedule(db: Session, data: ScheduleCreate, user_id: int) -> ReportSchedule:
    sched = ReportSchedule(
        user_id=user_id,
        dashboard_id=data.dashboard_id,
        recipient_email=data.recipient_email,
        frequency=data.frequency,
        send_hour=data.send_hour,
        send_minute=data.send_minute,
        day_of_week=data.day_of_week,
        day_of_month=data.day_of_month,
        timezone=data.timezone,
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    return sched


def update_schedule(db: Session, schedule_id: int, user_id: int, updates: dict) -> Optional[ReportSchedule]:
    sched = get_schedule(db, schedule_id, user_id)
    if not sched:
        return None
    for field, value in updates.items():
        if value is not None and hasattr(sched, field):
            setattr(sched, field, value)
    db.commit()
    db.refresh(sched)
    return sched


def get_schedule(db: Session, schedule_id: int, user_id: int) -> Optional[ReportSchedule]:
    return db.query(ReportSchedule).filter(
        ReportSchedule.id == schedule_id,
        ReportSchedule.user_id == user_id,
    ).first()


def get_schedules_for_user(db: Session, user_id: int) -> List[ReportSchedule]:
    return db.query(ReportSchedule).filter(
        ReportSchedule.user_id == user_id,
    ).order_by(ReportSchedule.created_at.desc()).all()


def get_schedules_for_dashboard(
    db: Session, dashboard_id: int, user_id: int
) -> List[ReportSchedule]:
    return db.query(ReportSchedule).filter(
        ReportSchedule.dashboard_id == dashboard_id,
        ReportSchedule.user_id == user_id,
    ).all()


def get_all_active_schedules(db: Session) -> List[ReportSchedule]:
    return db.query(ReportSchedule).filter(ReportSchedule.is_active == True).all()


def delete_schedule(db: Session, schedule_id: int, user_id: int) -> bool:
    sched = get_schedule(db, schedule_id, user_id)
    if not sched:
        return False
    db.delete(sched)
    db.commit()
    return True


def update_run_status(
    db: Session,
    schedule_id: int,
    next_run,
    last_run,
    status: str,
) -> None:
    sched = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
    if sched:
        sched.last_run  = last_run
        sched.next_run  = next_run
        sched.last_status = status
        db.commit()
