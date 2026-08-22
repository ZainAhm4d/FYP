"""
Anomaly Model
Stores detected anomalies per dataset column run.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from app.core.database import Base


class Anomaly(Base):
    __tablename__ = "anomalies"

    id            = Column(Integer, primary_key=True, index=True)
    dataset_id    = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    column_name   = Column(String,  nullable=False)
    method        = Column(String,  nullable=False, default="zscore")  # zscore | isolation_forest
    row_index     = Column(Integer, nullable=True)
    label         = Column(String,  nullable=True)   # time period or item name
    value         = Column(Float,   nullable=True)   # scalar; None for multivariate
    zscore        = Column(Float,   nullable=True)
    anomaly_score = Column(Float,   nullable=True)   # Isolation Forest normalised score
    severity      = Column(String,  nullable=False)  # low | medium | high
    extra         = Column(JSON,    nullable=True)   # multivariate value dict
    detected_at   = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":            self.id,
            "dataset_id":    self.dataset_id,
            "column_name":   self.column_name,
            "method":        self.method,
            "label":         self.label,
            "value":         self.value,
            "zscore":        self.zscore,
            "anomaly_score": self.anomaly_score,
            "severity":      self.severity,
            "extra":         self.extra,
            "detected_at":   self.detected_at.isoformat() if self.detected_at else None,
        }
