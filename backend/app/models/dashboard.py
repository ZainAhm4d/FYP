"""
Dashboard Model
Stores saved dashboard configurations
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Dashboard(Base):
    __tablename__ = "dashboards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Dashboard information
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Dashboard configuration (charts, layout, queries)
    config_json = Column(Text, nullable=False)  # JSON string with full dashboard state

    # Sharing
    share_token = Column(String, nullable=True, unique=True, index=True)
    is_public = Column(Boolean, nullable=False, default=False)
    view_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner            = relationship("User",                  back_populates="dashboards")
    report_schedules = relationship("ReportSchedule",        back_populates="dashboard", cascade="all, delete-orphan")
    collaborators    = relationship("DashboardCollaborator", back_populates="dashboard", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Dashboard(id={self.id}, name={self.name})>"
