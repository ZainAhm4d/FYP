"""
Analytics Services
"""
from .query_executor import QueryExecutor
from .anomaly_detection import detect_anomalies, detect_zscore, detect_isolation_forest, detect_trend_aware
from .forecasting import forecast_linear, build_forecast_plotly_traces

__all__ = [
    "QueryExecutor",
    "detect_anomalies", "detect_zscore", "detect_isolation_forest", "detect_trend_aware",
    "forecast_linear", "build_forecast_plotly_traces",
]
