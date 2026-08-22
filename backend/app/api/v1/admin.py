"""
Admin portal API (CH-18) — user lifecycle management.

Every route requires an admin account (`require_admin`). Deletion is SOFT:
the account is locked and anonymized immediately, kept recoverable for
`ADMIN_USER_RETENTION_DAYS`, then a daily scheduler job hard-purges the rows
AND the user's uploaded/processed files. Every mutation is audit-logged.
"""
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.config import settings
from app.core.security import validate_password
from app.crud import user as crud_user
from app.models.audit_log import AdminAuditLog
from app.models.dashboard import Dashboard
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.user import AdminStats, AdminUserCreate, AdminUserRow

router = APIRouter()


def _audit(db: Session, admin_id: int, action: str,
           target_id: Optional[int] = None, detail: str = "") -> None:
    db.add(AdminAuditLog(admin_user_id=admin_id, action=action,
                         target_user_id=target_id, detail=detail))
    db.commit()


def _user_or_404(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── Read ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserRow])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """All accounts (including soft-deleted) with per-user object counts."""
    ds_counts = dict(db.query(Dataset.user_id, func.count(Dataset.id))
                     .group_by(Dataset.user_id).all())
    db_counts = dict(db.query(Dashboard.user_id, func.count(Dashboard.id))
                     .group_by(Dashboard.user_id).all())
    rows = []
    for u in db.query(User).order_by(User.id).all():
        rows.append(AdminUserRow(
            id=u.id, email=u.email, full_name=u.full_name,
            is_active=u.is_active, is_admin=bool(getattr(u, "is_admin", False)),
            created_at=u.created_at,
            last_login_at=getattr(u, "last_login_at", None),
            deactivated_at=getattr(u, "deactivated_at", None),
            deleted_at=getattr(u, "deleted_at", None),
            dataset_count=ds_counts.get(u.id, 0),
            dashboard_count=db_counts.get(u.id, 0),
        ))
    return rows


@router.get("/stats", response_model=AdminStats)
def get_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    uploads_size = 0
    for root in (settings.UPLOAD_DIR, settings.PROCESSED_DIR):
        p = Path(root)
        if p.exists():
            uploads_size += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return AdminStats(
        total_users=db.query(User).count(),
        active_users=db.query(User).filter(User.is_active.is_(True)).count(),
        deleted_users=db.query(User).filter(User.deleted_at.isnot(None)).count(),
        total_datasets=db.query(Dataset).count(),
        total_dashboards=db.query(Dashboard).count(),
        uploads_size_bytes=uploads_size,
    )


@router.get("/audit")
def get_audit_log(
    limit: int = 200,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rows = (db.query(AdminAuditLog)
            .order_by(AdminAuditLog.id.desc())
            .limit(min(limit, 1000)).all())
    return [{
        "id": r.id, "admin_user_id": r.admin_user_id, "action": r.action,
        "target_user_id": r.target_user_id, "detail": r.detail,
        "created_at": r.created_at,
    } for r in rows]


# ── Mutations ─────────────────────────────────────────────────────────────────

@router.post("/users", response_model=AdminUserRow, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin onboarding — same password policy as self-registration."""
    if crud_user.get_user_by_email(db, email=body.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    ok, err = validate_password(body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    user = crud_user.create_user(db, body)
    if body.is_admin:
        user.is_admin = True
        db.commit()
        db.refresh(user)
    _audit(db, admin.id, "create_user", user.id, f"created {user.email}"
           + (" (admin)" if body.is_admin else ""))
    return AdminUserRow(
        id=user.id, email=user.email, full_name=user.full_name,
        is_active=user.is_active, is_admin=bool(user.is_admin),
        created_at=user.created_at,
    )


@router.put("/users/{user_id}/deactivate", response_model=AdminUserRow)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _user_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = False
    user.deactivated_at = datetime.utcnow()
    db.commit()
    _audit(db, admin.id, "deactivate", user.id, user.email)
    return AdminUserRow.model_validate(user)


@router.put("/users/{user_id}/reactivate", response_model=AdminUserRow)
def reactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _user_or_404(db, user_id)
    if user.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Account is deleted — restore it instead")
    user.is_active = True
    user.deactivated_at = None
    db.commit()
    _audit(db, admin.id, "reactivate", user.id, user.email)
    return AdminUserRow.model_validate(user)


def soft_delete_user(db: Session, user: User) -> None:
    """Shared by admin delete and self-service delete: lock the account,
    anonymize the email (frees it for re-registration), start the clock."""
    original = user.email
    user.deleted_at = datetime.utcnow()
    user.is_active = False
    user.email = f"deleted-{user.id}@account-removed.bidashboard.app"
    user.full_name = None
    db.commit()
    return original


@router.delete("/users/{user_id}", response_model=AdminUserRow)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _user_or_404(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account here")
    if getattr(user, "is_admin", False):
        admins_left = db.query(User).filter(
            User.is_admin.is_(True), User.deleted_at.is_(None), User.id != user.id
        ).count()
        if admins_left == 0:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin account")
    if user.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Account is already deleted")
    original = soft_delete_user(db, user)
    _audit(db, admin.id, "soft_delete", user.id,
           f"{original} — recoverable for {settings.ADMIN_USER_RETENTION_DAYS} days")
    return AdminUserRow.model_validate(user)


@router.post("/users/{user_id}/restore", response_model=AdminUserRow)
def restore_user(
    user_id: int,
    new_email: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Undo a soft delete within the retention window. The original email was
    anonymized at delete time, so a restore email must be provided (or the
    anonymized placeholder is kept for the admin to fix)."""
    user = _user_or_404(db, user_id)
    if user.deleted_at is None:
        raise HTTPException(status_code=400, detail="Account is not deleted")
    if new_email:
        if crud_user.get_user_by_email(db, email=new_email):
            raise HTTPException(status_code=400, detail="That email is already in use")
        user.email = new_email
    user.deleted_at = None
    user.is_active = True
    user.deactivated_at = None
    db.commit()
    _audit(db, admin.id, "restore", user.id, user.email)
    return AdminUserRow.model_validate(user)


# ── Retention purge (called by the daily scheduler job) ───────────────────────

def purge_deleted_users(db: Session) -> int:
    """Hard-delete accounts whose soft-delete window expired: all their rows
    (cascades cover datasets/dashboards/schedules) AND their files on disk.
    Returns the number of purged accounts."""
    cutoff = datetime.utcnow() - timedelta(days=settings.ADMIN_USER_RETENTION_DAYS)
    expired = db.query(User).filter(
        User.deleted_at.isnot(None), User.deleted_at < cutoff
    ).all()
    purged = 0
    for user in expired:
        uid = user.id
        for root in (settings.UPLOAD_DIR, settings.PROCESSED_DIR):
            d = os.path.join(root, f"user_{uid}")
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        db.delete(user)   # ORM cascade removes datasets/dashboards/schedules rows
        db.commit()
        db.add(AdminAuditLog(admin_user_id=0, action="purge", target_user_id=uid,
                             detail=f"retention window expired ({settings.ADMIN_USER_RETENTION_DAYS}d)"))
        db.commit()
        purged += 1
    return purged


# ── Startup seed ──────────────────────────────────────────────────────────────

def seed_admin_account(db: Session) -> None:
    """Idempotent: create the superadmin from ADMIN_EMAIL/ADMIN_PASSWORD env
    vars if configured and absent. Credentials are never logged."""
    email = settings.ADMIN_EMAIL
    password = settings.ADMIN_PASSWORD
    if not email or not password:
        return
    existing = crud_user.get_user_by_email(db, email=email)
    if existing:
        if not getattr(existing, "is_admin", False):
            existing.is_admin = True
            db.commit()
        return
    from app.schemas.user import UserCreate
    user = crud_user.create_user(db, UserCreate(email=email, password=password,
                                                full_name="Administrator"))
    user.is_admin = True
    db.commit()
