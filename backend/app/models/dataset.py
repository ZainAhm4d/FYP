"""
Dataset Model
Stores metadata about uploaded datasets
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Dataset(Base):
    __tablename__ = "datasets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # File information
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    
    # Dataset metadata
    row_count = Column(Integer, default=0)
    column_count = Column(Integer, default=0)
    data_types_json = Column(Text, nullable=True)  # JSON string of column types
    
    # Processing status
    cleaned_status = Column(Boolean, default=False)
    # 'processing' | 'ready' | 'failed' — cleaning runs in the background
    processing_status = Column(String, nullable=False, default='ready')
    upload_date = Column(DateTime, default=datetime.utcnow)

    # Live-data source (auto-refresh). 'upload' datasets never refresh.
    source_type = Column(String, nullable=False, default='upload')   # 'upload' | 'google_sheets'
    source_url = Column(String, nullable=True)                        # public sheet URL (safe to store)
    refresh_interval_minutes = Column(Integer, nullable=True)         # None = no auto-refresh
    last_refreshed = Column(DateTime, nullable=True)
    # Secret token for the push webhook (Apps Script onChange -> /ingest/{token})
    ingest_token = Column(String, nullable=True, unique=True, index=True)
    # CH-10: set whenever the push webhook fires — proves live push works
    last_push_at = Column(DateTime, nullable=True)
    
    # Relationships
    owner = relationship("User", back_populates="datasets")
    
    def __repr__(self):
        return f"<Dataset(id={self.id}, filename={self.filename})>"
