"""
User Model
Stores user authentication and profile information
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # CH-18: admin portal + account lifecycle
    is_admin       = Column(Boolean, default=False, nullable=False)
    deleted_at     = Column(DateTime, nullable=True)   # soft delete; purged after retention window
    deactivated_at = Column(DateTime, nullable=True)
    last_login_at  = Column(DateTime, nullable=True)
    
    # Relationships
    datasets         = relationship("Dataset",        back_populates="owner",     cascade="all, delete-orphan")
    dashboards       = relationship("Dashboard",      back_populates="owner",     cascade="all, delete-orphan")
    report_schedules = relationship("ReportSchedule", back_populates="owner",     cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
