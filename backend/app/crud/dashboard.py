"""
Dashboard CRUD Operations
Database operations for dashboard management
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.dashboard import Dashboard
from app.schemas.dashboard import DashboardCreate, DashboardUpdate


def get_dashboard(db: Session, dashboard_id: int, user_id: int) -> Optional[Dashboard]:
    """
    Get a single dashboard by ID for a specific user
    """
    return db.query(Dashboard).filter(
        Dashboard.id == dashboard_id,
        Dashboard.user_id == user_id
    ).first()


def get_dashboards(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Dashboard]:
    """
    Get all dashboards for a user, ordered by most recent first
    """
    return db.query(Dashboard).filter(
        Dashboard.user_id == user_id
    ).order_by(desc(Dashboard.updated_at)).offset(skip).limit(limit).all()


def create_dashboard(db: Session, dashboard: DashboardCreate, user_id: int) -> Dashboard:
    """
    Create a new dashboard
    """
    import json
    
    # Convert config_json dict to JSON string for storage
    config_json_str = json.dumps(dashboard.config_json)
    
    db_dashboard = Dashboard(
        user_id=user_id,
        name=dashboard.name,
        description=dashboard.description,
        config_json=config_json_str
    )
    
    db.add(db_dashboard)
    db.commit()
    db.refresh(db_dashboard)
    
    return db_dashboard


def update_dashboard(
    db: Session,
    dashboard_id: int,
    user_id: int,
    dashboard_update: DashboardUpdate
) -> Optional[Dashboard]:
    """
    Update an existing dashboard
    """
    import json
    from datetime import datetime
    
    db_dashboard = get_dashboard(db, dashboard_id, user_id)
    
    if not db_dashboard:
        return None
    
    # Update only provided fields
    update_data = dashboard_update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == "config_json" and value is not None:
            # Convert dict to JSON string
            value = json.dumps(value)
        setattr(db_dashboard, field, value)
    
    # Update timestamp
    db_dashboard.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_dashboard)
    
    return db_dashboard


def delete_dashboard(db: Session, dashboard_id: int, user_id: int) -> bool:
    """
    Delete a dashboard
    Returns True if deleted, False if not found
    """
    db_dashboard = get_dashboard(db, dashboard_id, user_id)
    
    if not db_dashboard:
        return False
    
    db.delete(db_dashboard)
    db.commit()
    
    return True


def count_user_dashboards(db: Session, user_id: int) -> int:
    """Count total dashboards for a user."""
    return db.query(Dashboard).filter(Dashboard.user_id == user_id).count()


def get_dashboard_by_token(db: Session, share_token: str) -> Optional[Dashboard]:
    """Return a public dashboard by its share token (no user check)."""
    return db.query(Dashboard).filter(
        Dashboard.share_token == share_token,
        Dashboard.is_public == True,
    ).first()


def enable_sharing(db: Session, dashboard_id: int, user_id: int) -> Optional[Dashboard]:
    """Generate a share token and mark the dashboard public."""
    import secrets
    db_dashboard = get_dashboard(db, dashboard_id, user_id)
    if not db_dashboard:
        return None
    if not db_dashboard.share_token:
        db_dashboard.share_token = secrets.token_urlsafe(24)
    db_dashboard.is_public = True
    db.commit()
    db.refresh(db_dashboard)
    return db_dashboard


def disable_sharing(db: Session, dashboard_id: int, user_id: int) -> Optional[Dashboard]:
    """Revoke the share token and mark the dashboard private."""
    db_dashboard = get_dashboard(db, dashboard_id, user_id)
    if not db_dashboard:
        return None
    db_dashboard.is_public = False
    db_dashboard.share_token = None
    db.commit()
    db.refresh(db_dashboard)
    return db_dashboard


def increment_view_count(db: Session, dashboard: Dashboard) -> None:
    """Increment the public view counter."""
    dashboard.view_count = (dashboard.view_count or 0) + 1
    db.commit()
