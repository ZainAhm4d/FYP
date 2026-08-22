"""
Scheduled Email Reports — REST endpoints.

POST   /schedules              create a new schedule
GET    /schedules              list all schedules for the current user
GET    /schedules/{id}         get a single schedule
DELETE /schedules/{id}         delete a schedule
POST   /schedules/{id}/send-now  trigger an immediate test send
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.crud import schedule as crud_schedule
from app.crud import dashboard as crud_dashboard
from app.models.user import User
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleResponse
from app.services.scheduler.report_scheduler import (
    add_schedule_job_from, next_run_from, remove_schedule_job,
)

router = APIRouter()


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a recurring email report for a dashboard."""
    # Verify the user owns the dashboard
    dashboard = crud_dashboard.get_dashboard(db, body.dashboard_id, current_user.id)
    if not dashboard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")

    sched = crud_schedule.create_schedule(db, body, current_user.id)

    # Set next_run and register the APScheduler job
    next_run = next_run_from(sched)
    from app.crud.schedule import update_run_status
    update_run_status(db, sched.id, next_run=next_run, last_run=None, status=None)
    db.refresh(sched)

    add_schedule_job_from(sched)

    return sched


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a schedule's recipient, frequency, time, day, or timezone."""
    sched = crud_schedule.update_schedule(
        db, schedule_id, current_user.id,
        body.model_dump(exclude_unset=True),
    )
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    # Recompute next_run and re-register the job with the new trigger
    next_run = next_run_from(sched)
    from app.crud.schedule import update_run_status
    update_run_status(db, sched.id, next_run=next_run, last_run=sched.last_run, status=sched.last_status)
    db.refresh(sched)

    if sched.is_active:
        add_schedule_job_from(sched)
    else:
        remove_schedule_job(sched.id)

    return sched


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all report schedules owned by the current user."""
    return crud_schedule.get_schedules_for_user(db, current_user.id)


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sched = crud_schedule.get_schedule(db, schedule_id, current_user.id)
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return sched


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a schedule and cancel its recurring job."""
    deleted = crud_schedule.delete_schedule(db, schedule_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    remove_schedule_job(schedule_id)
    return None


@router.post("/{schedule_id}/send-now", status_code=status.HTTP_202_ACCEPTED)
async def send_now(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an immediate test send of a scheduled report."""
    sched = crud_schedule.get_schedule(db, schedule_id, current_user.id)
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    # Run synchronously in the request thread (acceptable for a test send)
    from app.services.insights.summary_generator import (
        generate_dashboard_summary, render_html_email, render_pdf_report,
    )
    from app.services.email.email_sender import send_report_email

    dashboard = sched.dashboard

    # Pull latest source data + re-execute chart queries before generating
    try:
        import json as _json
        from app.services.data_refresh import refresh_dataset, refresh_dashboard_data
        from app.models.dataset import Dataset as DatasetModel
        cfg = _json.loads(dashboard.config_json)
        ds_ids = {(c.get("dataset") or {}).get("id")
                  for c in cfg.get("charts", []) if (c.get("dataset") or {}).get("id")}
        for ds_id in ds_ids:
            ds = db.query(DatasetModel).filter(DatasetModel.id == ds_id).first()
            if ds and ds.source_type == "google_sheets" and ds.source_url:
                refresh_dataset(db, ds)
        refresh_dashboard_data(db, dashboard)
        db.refresh(dashboard)
    except Exception:
        pass   # send with stored data rather than failing the test send

    summary   = generate_dashboard_summary(dashboard)
    html_body = render_html_email(summary, sched.frequency)
    pdf_bytes = render_pdf_report(summary, sched.frequency)

    safe_name    = dashboard.name.replace(" ", "_").replace("/", "-")[:40]
    pdf_filename = f"{safe_name}_report.pdf"

    ok = send_report_email(
        recipient=sched.recipient_email,
        subject=f"[Test] {dashboard.name} — {sched.frequency.capitalize()} Report",
        html_body=html_body,
        pdf_bytes=pdf_bytes or None,
        pdf_filename=pdf_filename,
    )

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Email could not be delivered. Check SENDGRID_API_KEY or SMTP_HOST in .env.",
        )

    return {"detail": f"Report sent to {sched.recipient_email}"}
