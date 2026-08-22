"""DashboardCollaborator model — links users to dashboards with a role."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base


class DashboardCollaborator(Base):
    __tablename__ = "dashboard_collaborators"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "user_id", name="uq_dashboard_collaborator"),
    )

    id           = Column(Integer, primary_key=True, index=True)
    dashboard_id = Column(Integer, ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id      = Column(Integer, ForeignKey("users.id",      ondelete="CASCADE"), nullable=False, index=True)
    invited_by   = Column(Integer, ForeignKey("users.id",      ondelete="SET NULL"), nullable=True)
    role         = Column(String, nullable=False, default="viewer")  # "viewer" | "editor"
    created_at   = Column(DateTime, default=datetime.utcnow)

    dashboard = relationship("Dashboard", back_populates="collaborators")
    user      = relationship("User", foreign_keys=[user_id])
    inviter   = relationship("User", foreign_keys=[invited_by])
