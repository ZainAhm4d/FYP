"""
Pattern detection helpers for insight generation.
All functions are stateless and return plain dicts.
"""
from typing import Dict, List, Any, Optional


def detect_trend(data: List[Dict], avg: float) -> Dict[str, Any]:
    """Trend direction, magnitude, and confidence from time-series data."""
    if len(data) < 2:
        return {"direction": "insufficient_data"}

    values = [d["value"] for d in data]
    first, last = values[0], values[-1]

    if first == 0:
        return {"direction": "unknown"}

    pct_change = (last - first) / abs(first) * 100

    if pct_change > 5:
        direction = "up"
    elif pct_change < -5:
        direction = "down"
    else:
        direction = "stable"

    strength = "strong" if abs(pct_change) > 25 else "mild"
    # Confidence scales with magnitude, capped at 0.95
    confidence = min(0.95, 0.55 + abs(pct_change) / 120)

    return {
        "direction":   direction,
        "strength":    strength,
        "pct_change":  pct_change,
        "start_label": data[0].get("time", "start"),
        "end_label":   data[-1].get("time", "end"),
        "start_value": first,
        "end_value":   last,
        "confidence":  round(confidence, 2),
    }


def detect_peak_trough(data: List[Dict], avg: float) -> Dict[str, Any]:
    """Return peak and trough points that are meaningfully far from the mean."""
    if len(data) < 3 or avg == 0:
        return {}

    values = [d["value"] for d in data]
    times  = [data[i].get("time", str(i)) for i in range(len(data))]

    max_val = max(values)
    min_val = min(values)
    peak_idx   = values.index(max_val)
    trough_idx = values.index(min_val)

    result: Dict[str, Any] = {}

    peak_pct = (max_val - avg) / abs(avg) * 100
    if peak_pct > 10:
        result["peak"] = {
            "period":        times[peak_idx],
            "value":         max_val,
            "pct_above_avg": peak_pct,
        }

    trough_pct = (avg - min_val) / abs(avg) * 100
    if trough_pct > 10:
        result["trough"] = {
            "period":        times[trough_idx],
            "value":         min_val,
            "pct_below_avg": trough_pct,
        }

    return result


def detect_sudden_change(data: List[Dict]) -> Optional[Dict[str, Any]]:
    """Find the single largest period-over-period percentage move."""
    if len(data) < 2:
        return None

    best: Optional[Dict] = None
    best_abs = 0.0

    for i in range(1, len(data)):
        prev = data[i - 1]["value"]
        curr = data[i]["value"]
        if prev == 0:
            continue
        pct = (curr - prev) / abs(prev) * 100
        if abs(pct) > best_abs:
            best_abs = abs(pct)
            best = {
                "from_label": data[i - 1].get("time", str(i - 1)),
                "to_label":   data[i].get("time", str(i)),
                "from_value": prev,
                "to_value":   curr,
                "pct":        pct,
            }

    return best if best and best_abs > 20 else None


def detect_category_concentration(
    data: List[Dict],
    total: float,
    value_key: str = "value",
    name_key: str = "category",
    k: int = 3,
) -> Dict[str, Any]:
    """
    Compute top-k share of total and gap between #1 and #2.
    Works for both category_comparison (key='category') and top_k (key='item').
    """
    if not data or total == 0:
        return {}

    sorted_data = sorted(data, key=lambda x: x.get(value_key, 0), reverse=True)
    top_k_total = sum(d.get(value_key, 0) for d in sorted_data[:k])
    pct = top_k_total / total * 100

    result: Dict[str, Any] = {"k": min(k, len(data)), "pct": pct}

    if len(sorted_data) > 1:
        first_val  = sorted_data[0].get(value_key, 0)
        second_val = sorted_data[1].get(value_key, 0)
        second_name = sorted_data[1].get(name_key) or sorted_data[1].get("item", "")
        if first_val != 0:
            gap_pct = (first_val - second_val) / abs(first_val) * 100
            result["gap_pct_to_second"] = gap_pct
            result["second_name"]       = second_name

    return result
