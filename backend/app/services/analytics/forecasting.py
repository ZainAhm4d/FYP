"""
Time-series forecasting service.

Uses ordinary least-squares linear regression (numpy) + scipy t-distribution
prediction intervals — no additional dependencies beyond what's already installed.

Entry point:
    forecast_linear(data, n_periods, confidence)
        data: list of {"time": str, "value": float} dicts (sorted chronologically)
        Returns a dict with "fitted", "forecast", "r_squared", "trend", "method"
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import numpy as np


# ── Period-label arithmetic ───────────────────────────────────────────────────

def _next_period_label(base_label: str, step: int) -> str:
    """Extrapolate a human-readable period label `step` units beyond `base_label`."""

    # YYYY-MM (monthly)
    m = re.match(r"^(\d{4})-(\d{2})$", base_label)
    if m:
        yr, mo = int(m.group(1)), int(m.group(2))
        mo += step
        yr += (mo - 1) // 12
        mo = ((mo - 1) % 12) + 1
        return f"{yr:04d}-{mo:02d}"

    # YYYY-Qn (quarterly)
    m = re.match(r"^(\d{4})-Q(\d)$", base_label)
    if m:
        yr, q = int(m.group(1)), int(m.group(2))
        q += step
        yr += (q - 1) // 4
        q = ((q - 1) % 4) + 1
        return f"{yr:04d}-Q{q}"

    # YYYY-WNN (weekly)
    m = re.match(r"^(\d{4})-W(\d+)$", base_label)
    if m:
        yr, wk = int(m.group(1)), int(m.group(2))
        wk += step
        while wk > 52:
            wk -= 52
            yr += 1
        return f"{yr:04d}-W{wk:02d}"

    # YYYY (yearly)
    m = re.match(r"^(\d{4})$", base_label)
    if m:
        return str(int(m.group(1)) + step)

    # YYYY-MM-DD (daily) — add days
    m = re.match(r"^(\d{4}-\d{2}-\d{2})$", base_label)
    if m:
        try:
            import datetime
            d = datetime.date.fromisoformat(base_label) + datetime.timedelta(days=step)
            return d.isoformat()
        except Exception:
            pass

    return f"{base_label}+{step}"


def _infer_period_gap(labels: List[str]) -> int:
    """Return the median integer gap implied by the last few labels (for weekly etc.)."""
    return 1   # default; individual handlers carry unit semantics


# ── Core forecasting ──────────────────────────────────────────────────────────

def forecast_linear(
    data: List[Dict[str, Any]],
    n_periods: int = 6,
    confidence: float = 0.95,
) -> Dict[str, Any]:
    """
    Fit a linear trend (OLS) on aggregated time-series data and project forward.

    Args:
        data:       Sorted list of {"time": str, "value": float/int} dicts.
        n_periods:  How many future periods to project.
        confidence: Width of the prediction interval (default 95 %).

    Returns:
        {
            "fitted":            [{"time", "value"}, ...],       # in-sample OLS line
            "forecast":          [{"time","value","lower","upper","is_forecast"}, ...],
            "r_squared":         float,
            "trend":             "up" | "down" | "flat",
            "slope_per_period":  float,
            "n_periods":         int,
            "confidence":        float,
            "method":            "linear_regression",
        }
        or {"error": str} on failure.
    """
    if not data:
        return {"error": "No data provided"}
    if len(data) < 3:
        return {"error": f"Need at least 3 data points to forecast (got {len(data)})"}

    try:
        from scipy import stats as _stats
        _has_scipy = True
    except ImportError:
        _has_scipy = False

    values = np.array([float(d.get("value", 0) or 0) for d in data], dtype=float)
    n = len(values)
    x = np.arange(n, dtype=float)

    # OLS via numpy
    coeffs   = np.polyfit(x, values, 1)
    slope, intercept = float(coeffs[0]), float(coeffs[1])
    fitted_vals = slope * x + intercept

    # Residuals
    residuals = values - fitted_vals
    df_err    = max(n - 2, 1)
    mse       = float(np.sum(residuals ** 2) / df_err)
    se        = float(np.sqrt(mse))

    # R²
    ss_tot    = float(np.sum((values - values.mean()) ** 2))
    ss_res    = float(np.sum(residuals ** 2))
    r_squared = max(0.0, 1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    # t-critical value for prediction interval
    if _has_scipy:
        alpha = 1.0 - confidence
        t_crit = float(_stats.t.ppf(1 - alpha / 2, df=df_err))
    else:
        # Rough 95% approximation
        t_crit = 2.0

    x_mean = float(x.mean())
    ss_x   = float(np.sum((x - x_mean) ** 2)) or 1.0

    last_label = str(data[-1].get("time", ""))

    # Future prediction intervals
    forecast_points = []
    for i in range(1, n_periods + 1):
        fx  = float(n - 1 + i)
        fv  = slope * fx + intercept
        # Prediction SE (wider than confidence SE — accounts for individual variation)
        se_pred = se * float(np.sqrt(1 + 1 / n + (fx - x_mean) ** 2 / ss_x))
        margin  = t_crit * se_pred
        label   = _next_period_label(last_label, i)
        forecast_points.append({
            "time":        label,
            "value":       round(fv, 4),
            "lower":       round(fv - margin, 4),
            "upper":       round(fv + margin, 4),
            "is_forecast": True,
        })

    # Trend classification (% change from first to last fitted value)
    if fitted_vals[0] != 0:
        pct = (fitted_vals[-1] - fitted_vals[0]) / abs(fitted_vals[0]) * 100
    else:
        pct = 0.0
    trend = "up" if pct > 2 else "down" if pct < -2 else "flat"

    return {
        "fitted": [
            {"time": d.get("time", str(i)), "value": round(float(fv), 4)}
            for i, (d, fv) in enumerate(zip(data, fitted_vals))
        ],
        "forecast":          forecast_points,
        "r_squared":         round(r_squared, 4),
        "trend":             trend,
        "slope_per_period":  round(slope, 4),
        "n_periods":         n_periods,
        "confidence":        confidence,
        "method":            "linear_regression",
    }


def build_forecast_plotly_traces(
    original_data: List[Dict[str, Any]],
    forecast_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Convert forecast_linear() output into Plotly trace dicts that can be
    appended to an existing chart with Plotly.addTraces().

    Returns a list of 3 traces:
      0 — Trend line  (solid grey, covers historical data)
      1 — Confidence band fill (light purple shaded area)
      2 — Forecast line (dashed purple, future only, with hover)
    """
    if "error" in forecast_result:
        return []

    fitted   = forecast_result.get("fitted", [])
    forecast = forecast_result.get("forecast", [])

    if not fitted or not forecast:
        return []

    # Connect last historical point to first forecast point for continuity
    last_hist = {"time": fitted[-1]["time"], "value": fitted[-1]["value"]}

    # Trend line (historical)
    trend_trace = {
        "x":    [p["time"]  for p in fitted],
        "y":    [p["value"] for p in fitted],
        "mode": "lines",
        "name": "Trend (OLS fit)",
        "line": {"color": "#6b7280", "width": 1.5, "dash": "dot"},
        "hovertemplate": "Trend: %{y:,.0f}<extra></extra>",
        "showlegend": True,
        "type": "scatter",
    }

    # Confidence band — filled area between upper and lower
    upper_x = [last_hist["time"]] + [p["time"]  for p in forecast]
    upper_y = [last_hist["value"]] + [p["upper"] for p in forecast]
    lower_x = [last_hist["time"]] + [p["time"]  for p in reversed(forecast)]
    lower_y = [last_hist["value"]] + [p["lower"] for p in reversed(forecast)]

    band_trace = {
        "x":          upper_x + lower_x,
        "y":          upper_y + lower_y,
        "fill":       "toself",
        "fillcolor":  "rgba(139, 92, 246, 0.12)",
        "line":       {"color": "rgba(0,0,0,0)"},
        "name":       f"{int(forecast_result.get('confidence', 0.95)*100)}% Prediction Interval",
        "hoverinfo":  "skip",
        "showlegend": True,
        "type":       "scatter",
    }

    # Forecast line (connects last historical point to future)
    forecast_x = [last_hist["time"]] + [p["time"]  for p in forecast]
    forecast_y = [last_hist["value"]] + [p["value"] for p in forecast]

    r2 = forecast_result.get("r_squared", 0)
    trend_emoji = {"up": "↑", "down": "↓", "flat": "→"}.get(
        forecast_result.get("trend", "flat"), "→"
    )

    forecast_trace = {
        "x":    forecast_x,
        "y":    forecast_y,
        "mode": "lines+markers",
        "name": f"Forecast {trend_emoji} (R²={r2:.2f})",
        "line": {"color": "#7c3aed", "width": 2.5, "dash": "dash"},
        "marker": {"size": 6, "color": "#7c3aed", "symbol": "circle-open"},
        "hovertemplate": "Forecast %{x}: %{y:,.0f}<extra></extra>",
        "showlegend": True,
        "type": "scatter",
    }

    return [trend_trace, band_trace, forecast_trace]
