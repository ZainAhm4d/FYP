"""
QueryHistory Model
Records every executed query for replay and auditing.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text

from app.core.database import Base


class QueryHistory(Base):
    __tablename__ = "query_history"

    id                = Column(Integer, primary_key=True, index=True)
    dataset_id        = Column(Integer, nullable=False, index=True)
    user_id           = Column(Integer, nullable=False, index=True)
    template_type     = Column(String,  nullable=False)
    query_text        = Column(Text,    nullable=True)   # populated for NLP queries
    parameters_json   = Column(Text,    nullable=False, default="{}")
    nlp_mode          = Column(String,  nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    created_at        = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<QueryHistory(id={self.id}, dataset={self.dataset_id}, type={self.template_type})>"
