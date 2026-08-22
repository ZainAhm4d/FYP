"""Report Schedule Model — stores recurring email report configurations."""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    dashboard_id  = Column(Integer, ForeignKey("dashboards.id"), nullable=False)

    recipient_email = Column(String, nullable=False)
    frequency       = Column(String, nullable=False)   # daily | weekly | monthly
    is_active       = Column(Boolean, nullable=False, default=True)

    # When exactly to send (interpreted in `timezone`)
    send_hour    = Column(Integer, nullable=False, default=8)    # 0-23
    send_minute  = Column(Integer, nullable=False, default=0)    # 0-59
    day_of_week  = Column(Integer, nullable=True)                # 0=Mon … 6=Sun (weekly)
    day_of_month = Column(Integer, nullable=True)                # 1-31 (monthly); clamped to the month's last day if shorter
    timezone     = Column(String, nullable=False, default="UTC") # IANA name, e.g. "Asia/Karachi"

    next_run  = Column(DateTime, nullable=True)
    last_run  = Column(DateTime, nullable=True)
    last_status = Column(String, nullable=True)       # 'sent' | 'failed' | None

    created_at = Column(DateTime, default=datetime.utcnow)

    owner     = relationship("User",      back_populates="report_schedules")
    dashboard = relationship("Dashboard", back_populates="report_schedules")

    def __repr__(self) -> str:
        return f"<ReportSchedule(id={self.id}, freq={self.frequency}, email={self.recipient_email})>"
