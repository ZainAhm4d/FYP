"""AdminAuditLog — every admin mutation leaves a row (CH-18)."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime

from app.core.database import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id             = Column(Integer, primary_key=True, index=True)
    admin_user_id  = Column(Integer, nullable=False, index=True)
    action         = Column(String, nullable=False)   # create_user | deactivate | reactivate | soft_delete | restore | purge | self_delete
    target_user_id = Column(Integer, nullable=True, index=True)
    detail         = Column(String, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
