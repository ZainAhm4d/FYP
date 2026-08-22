"""DatasetRelationship — a join link between two datasets (Power BI model-view style)."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.core.database import Base


class DatasetRelationship(Base):
    __tablename__ = "dataset_relationships"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    left_dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    left_column      = Column(String, nullable=False)
    right_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    right_column     = Column(String, nullable=False)
    join_type        = Column(String, nullable=False, default="inner")  # inner | left | right | outer
    # CH-09: inferred key relationship (one_to_one / one_to_many / many_to_one / many_to_many)
    cardinality      = Column(String, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
