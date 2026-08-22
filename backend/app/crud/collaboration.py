"""CRUD helpers for dashboard_collaborators table."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.collaboration import DashboardCollaborator
from app.models.user import User
from app.models.dashboard import Dashboard


def _get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def _assert_owner(db: Session, dashboard_id: int, owner_id: int) -> Dashboard:
    d = db.query(Dashboard).filter(
        Dashboard.id == dashboard_id,
        Dashboard.user_id == owner_id,
    ).first()
    if not d:
        return None
    return d


def invite_collaborator(
    db: Session,
    dashboard_id: int,
    owner_id: int,
    email: str,
    role: str,
) -> tuple:
    """
    Add a collaborator to a dashboard.
    Returns (collaborator_or_None, error_str_or_None).
    """
    dashboard = _assert_owner(db, dashboard_id, owner_id)
    if not dashboard:
        return None, "Dashboard not found or you are not the owner"

    target = _get_user_by_email(db, email)
    if not target:
        return None, f"No account found for {email}"

    if target.id == owner_id:
        return None, "You cannot invite yourself"

    existing = db.query(DashboardCollaborator).filter(
        DashboardCollaborator.dashboard_id == dashboard_id,
        DashboardCollaborator.user_id == target.id,
    ).first()

    if existing:
        existing.role = role
        db.commit()
        db.refresh(existing)
        return existing, None

    collab = DashboardCollaborator(
        dashboard_id=dashboard_id,
        user_id=target.id,
        invited_by=owner_id,
        role=role,
    )
    db.add(collab)
    db.commit()
    db.refresh(collab)
    return collab, None


def list_collaborators(db: Session, dashboard_id: int, owner_id: int) -> tuple:
    """Returns (list_of_collaborators, error_str_or_None)."""
    dashboard = _assert_owner(db, dashboard_id, owner_id)
    if not dashboard:
        return None, "Dashboard not found or you are not the owner"
    collabs = db.query(DashboardCollaborator).filter(
        DashboardCollaborator.dashboard_id == dashboard_id,
    ).all()
    return collabs, None


def update_role(
    db: Session,
    dashboard_id: int,
    collaborator_id: int,
    owner_id: int,
    role: str,
) -> tuple:
    if not _assert_owner(db, dashboard_id, owner_id):
        return None, "Dashboard not found or you are not the owner"
    collab = db.query(DashboardCollaborator).filter(
        DashboardCollaborator.id == collaborator_id,
        DashboardCollaborator.dashboard_id == dashboard_id,
    ).first()
    if not collab:
        return None, "Collaborator not found"
    collab.role = role
    db.commit()
    db.refresh(collab)
    return collab, None


def revoke(
    db: Session,
    dashboard_id: int,
    collaborator_id: int,
    owner_id: int,
) -> tuple:
    if not _assert_owner(db, dashboard_id, owner_id):
        return None, "Dashboard not found or you are not the owner"
    collab = db.query(DashboardCollaborator).filter(
        DashboardCollaborator.id == collaborator_id,
        DashboardCollaborator.dashboard_id == dashboard_id,
    ).first()
    if not collab:
        return None, "Collaborator not found"
    db.delete(collab)
    db.commit()
    return True, None


def get_user_role(db: Session, dashboard_id: int, user_id: int) -> Optional[str]:
    """Return the collaborator role for user_id on dashboard_id, or None."""
    collab = db.query(DashboardCollaborator).filter(
        DashboardCollaborator.dashboard_id == dashboard_id,
        DashboardCollaborator.user_id == user_id,
    ).first()
    return collab.role if collab else None
