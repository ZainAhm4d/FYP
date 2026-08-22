"""
Anomaly Detection Service
Detects statistical outliers in dataset columns using:
  - Z-score (univariate, best for time-series trend analysis)
  - Isolation Forest (multivariate, best for whole-dataset scans)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Severity thresholds (multiples of the base Z-score threshold)
_SEVERITY_HIGH   = 2.0   # z >= threshold * 2.0  → high
_SEVERITY_MEDIUM = 1.4   # z >= threshold * 1.4  → medium
                          # z >= threshold         → low

SEVERITY_COLORS = {
    "high":   "#EF4444",   # red
    "medium": "#F97316",   # orange
    "low":    "#EAB308",   # yellow
}


def _zscore_severity(z: float, threshold: float) -> str:
    if z >= threshold * _SEVERITY_HIGH:
        return "high"
    if z >= threshold * _SEVERITY_MEDIUM:
        return "medium"
    return "low"


def detect_zscore(
    series: pd.Series,
    threshold: float = 3.0,
    label_series: Optional[pd.Series] = None,
) -> List[Dict[str, Any]]:
    """
    Z-score anomaly detection on a single numeric series.

    Args:
        series:       Numeric values to analyse (e.g. aggregated metric per period).
        threshold:    Sigma level above which a point is anomalous (default 3σ).
        label_series: Optional matching series of labels (e.g. time periods).

    Returns:
        List of anomaly dicts: {index, label, value, zscore, severity, method}.
    """
    series = series.dropna()
    if len(series) < 4:
        return []

    mean = float(series.mean())
    std  = float(series.std())
    if std == 0:
        return []

    anomalies: List[Dict[str, Any]] = []
    for pos, (idx, val) in enumerate(series.items()):
        z = abs((float(val) - mean) / std)
        if z >= threshold:
            label = str(label_series.iloc[pos]) if label_series is not None else str(idx)
            anomalies.append({
                "index":    pos,
                "label":    label,
                "value":    float(val),
                "zscore":   round(z, 3),
                "severity": _zscore_severity(z, threshold),
                "method":   "zscore",
            })

    return anomalies


def detect_isolation_forest(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    contamination: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Isolation Forest anomaly detection (multivariate).

    Args:
        df:            DataFrame to scan.
        columns:       Numeric columns to use (all numeric if None).
        contamination: Expected proportion of outliers (0–0.5).

    Returns:
        List of anomaly dicts: {row_index, value_summary, score, severity, method}.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        logger.warning("scikit-learn not installed — Isolation Forest unavailable")
        return []

    num_cols = columns or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    num_cols = [c for c in num_cols if c in df.columns]

    if not num_cols or len(df) < 10:
        return []

    X = df[num_cols].dropna()
    if len(X) < 10:
        return []

    model = IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)
    preds  = model.fit_predict(X)        # -1 = anomaly, 1 = normal
    scores = model.decision_function(X)  # more negative = more anomalous

    # Normalise scores to 0–1 (higher = more anomalous)
    s_min, s_max = scores.min(), scores.max()
    norm = (scores - s_max) / (s_min - s_max + 1e-9) if s_min != s_max else np.zeros_like(scores)

    anomalies: List[Dict[str, Any]] = []
    for i, (pred, score, nscore) in enumerate(zip(preds, scores, norm)):
        if pred == -1:
            row_idx = int(X.index[i])
            severity = "high" if nscore >= 0.7 else "medium" if nscore >= 0.4 else "low"
            anomalies.append({
                "index":         row_idx,
                "label":         f"Row {row_idx}",
                "value":         {c: float(df.loc[row_idx, c]) for c in num_cols
                                  if pd.notna(df.loc[row_idx, c])},
                "zscore":        None,
                "anomaly_score": round(float(nscore), 3),
                "severity":      severity,
                "method":        "isolation_forest",
            })

    return anomalies


def detect_trend_aware(
    series: pd.Series,
    threshold: float = 3.0,
    label_series: Optional[pd.Series] = None,
    poly_degree: int = 1,
) -> List[Dict[str, Any]]:
    """
    Trend-aware Z-score anomaly detection.

    Fits a polynomial trend (default: linear) to remove the underlying trend
    before running Z-score detection on the detrended residuals.  This avoids
    false positives that appear simply because the series is rising or falling
    monotonically.

    Args:
        series:       Numeric time-series values.
        threshold:    Sigma threshold (same semantics as detect_zscore).
        label_series: Optional period labels aligned with `series`.
        poly_degree:  Degree of the polynomial fit (1 = linear, 2 = quadratic).

    Returns:
        List of anomaly dicts with an extra key "detrended_zscore".
    """
    series = series.dropna()
    if len(series) < 6:
        # Fall back to standard Z-score when there's too little data to detrend
        return detect_zscore(series, threshold=threshold, label_series=label_series)

    x = np.arange(len(series), dtype=float)
    y = series.values.astype(float)

    # Fit polynomial trend and compute residuals
    try:
        coeffs   = np.polyfit(x, y, poly_degree)
        trend    = np.polyval(coeffs, x)
        residuals = pd.Series(y - trend, index=series.index)
    except Exception:
        return detect_zscore(series, threshold=threshold, label_series=label_series)

    mean_r = float(residuals.mean())
    std_r  = float(residuals.std())
    if std_r == 0:
        return []

    anomalies: List[Dict[str, Any]] = []
    for pos, (idx, res) in enumerate(residuals.items()):
        z = abs((float(res) - mean_r) / std_r)
        if z >= threshold:
            label = str(label_series.iloc[pos]) if label_series is not None else str(idx)
            orig_val = float(series.iloc[pos])
            anomalies.append({
                "index":           pos,
                "label":           label,
                "value":           orig_val,
                "zscore":          round(z, 3),
                "detrended_zscore": round(z, 3),
                "severity":        _zscore_severity(z, threshold),
                "method":          "trend_aware_zscore",
            })

    return anomalies


def _numeric_like_columns(df: pd.DataFrame) -> List[str]:
    """
    Columns worth z-score scanning: real numeric dtype, OR text columns that
    are mostly-parseable numbers (currency/comma-formatted, e.g. "$1,200") —
    matching the same currency/format-aware parsing the rest of the app uses,
    not just a raw dtype check (which would silently skip those columns).
    """
    from app.services.data_processing.type_detector import parse_numeric_series

    cols = []
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
            continue
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
            try:
                parsed, _info = parse_numeric_series(df[c])
                non_null = df[c].notna().sum()
                if non_null and parsed.notna().sum() / non_null >= 0.8:
                    cols.append(c)
            except Exception:
                continue
    return cols


def _parse_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """Currency/format-aware numeric parse (not plain pd.to_numeric, which
    would turn every "$1,200"-style cell into NaN and silently drop it)."""
    if pd.api.types.is_numeric_dtype(df[column]):
        return pd.to_numeric(df[column], errors="coerce")
    from app.services.data_processing.type_detector import parse_numeric_series
    parsed, _info = parse_numeric_series(df[column])
    return parsed


def detect_anomalies(
    df: pd.DataFrame,
    column: Optional[str] = None,
    method: str = "auto",
    threshold: float = 3.0,
    contamination: float = 0.05,
    label_column: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Unified entry point for anomaly detection.

    method='auto':
      - single column  → zscore
      - multi-column   → isolation_forest
    method='zscore'           → Z-score on `column`, or on EVERY numeric-like
                                 column if none is specified (previously this
                                 silently scanned only the first numeric
                                 column and dropped every other one).
    method='isolation_forest' → Isolation Forest on all / specified columns
    """
    if method == "auto":
        method = "zscore" if column else "isolation_forest"

    if method == "zscore":
        labels = df[label_column] if label_column and label_column in df.columns else None

        if column is not None:
            series = _parse_numeric(df, column)
            results = detect_zscore(series, threshold=threshold, label_series=labels)
            for a in results:
                a["column_name"] = column
            return results

        # No column specified — scan EVERY numeric-like column, not just the
        # first one, and tag each result with the column it came from.
        all_results: List[Dict[str, Any]] = []
        for col in _numeric_like_columns(df):
            series = _parse_numeric(df, col)
            for a in detect_zscore(series, threshold=threshold, label_series=labels):
                a["column_name"] = col
                all_results.append(a)
        all_results.sort(key=lambda a: a.get("zscore") or 0, reverse=True)
        return all_results

    return detect_isolation_forest(df, columns=[column] if column else None,
                                   contamination=contamination)
