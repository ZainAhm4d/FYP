"""
Narrative Generator — orchestrates pattern detection and template filling
to produce structured insight dicts consumed by the API and frontend.

Each insight is:
    {"text": str, "type": str, "confidence": float}

Types: summary | trend_up | trend_down | trend_stable | top_performer |
       peak | trough | sudden_change | anomaly | correlation | concentration |
       distribution
"""
from typing import Dict, List, Any

from app.services.insights import insight_templates as T
from app.services.insights.pattern_detector import (
    detect_trend,
    detect_peak_trough,
    detect_sudden_change,
    detect_category_concentration,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _i(text: str, type_: str, confidence: float = 0.8) -> Dict[str, Any]:
    return {"text": text, "type": type_, "confidence": round(confidence, 2)}


# ── Public entry point ────────────────────────────────────────────────────────

def generate_insights(
    template_type: str,
    query_result: Dict[str, Any],
    parameters: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate a list of structured insight dicts from query results.

    Args:
        template_type: One of the five query template types.
        query_result:  Output from QueryExecutor.execute_query().
        parameters:    Original query parameters (column names, k, etc.).

    Returns:
        List of {"text", "type", "confidence"} dicts, ordered by importance.
    """
    data    = query_result.get("data", [])
    summary = query_result.get("summary", {})

    if not data:
        return [_i("No data available for analysis.", "summary", 1.0)]

    dispatch = {
        "trend_over_time":       _trend_insights,
        "category_comparison":   _category_insights,
        "top_k_items":           _top_k_insights,
        "scatter_relationship":  _scatter_insights,
        "distribution_analysis": _distribution_insights,
        "correlation_analysis":  _correlation_insights,
        "grouped_aggregation":   _grouped_agg_insights,
        "period_over_period":    _period_insights,
    }
    handler = dispatch.get(template_type)
    if handler is None:
        return [_i(f"Showing {len(data)} data points.", "summary", 1.0)]

    return handler(data, summary, parameters, query_result)


# ── Per-template generators ───────────────────────────────────────────────────

def _trend_insights(data, summary, params, query_result) -> List[Dict]:
    metric  = params.get("metric_column", "metric")
    total   = summary.get("total", 0)
    avg     = summary.get("average", 0)
    periods = summary.get("periods", len(data))
    insights: List[Dict] = []

    # 1. Summary line
    insights.append(_i(
        T.PERIOD_SUMMARY.format(metric=metric, total=total, avg=avg, periods=periods),
        "summary", 0.95,
    ))

    # 2. Trend direction
    trend     = detect_trend(data, avg)
    direction = trend.get("direction", "unknown")
    pct       = trend.get("pct_change", 0)
    conf      = trend.get("confidence", 0.75)

    if direction == "up":
        tmpl = T.TREND_UP_STRONG if trend.get("strength") == "strong" else T.TREND_UP_MILD
        insights.append(_i(
            tmpl.format(metric=metric, pct=abs(pct),
                        start_label=trend["start_label"], end_label=trend["end_label"]),
            "trend_up", conf,
        ))
    elif direction == "down":
        tmpl = T.TREND_DOWN_STRONG if trend.get("strength") == "strong" else T.TREND_DOWN_MILD
        insights.append(_i(
            tmpl.format(metric=metric, pct=abs(pct),
                        start_label=trend["start_label"], end_label=trend["end_label"]),
            "trend_down", conf,
        ))
    elif direction == "stable" and avg != 0:
        max_v     = summary.get("max", avg)
        min_v     = summary.get("min", avg)
        range_pct = (max_v - min_v) / abs(avg) * 100
        insights.append(_i(
            T.TREND_STABLE.format(metric=metric, periods=periods, range_pct=range_pct),
            "trend_stable", 0.8,
        ))

    # 3. Peak and trough
    pt = detect_peak_trough(data, avg)
    if "peak" in pt:
        p = pt["peak"]
        insights.append(_i(
            T.PEAK_FINDING.format(period=p["period"], value=p["value"], pct=p["pct_above_avg"]),
            "peak", 0.85,
        ))
    if "trough" in pt:
        t = pt["trough"]
        insights.append(_i(
            T.TROUGH_FINDING.format(period=t["period"], value=t["value"], pct=t["pct_below_avg"]),
            "trough", 0.85,
        ))

    # 4. Biggest jump
    jump = detect_sudden_change(data)
    if jump:
        insights.append(_i(
            T.SUDDEN_JUMP.format(**jump),
            "sudden_change", 0.8,
        ))

    # 5. Anomaly call-outs (high severity only, max 2)
    anomalies = query_result.get("anomalies") or []
    high = [a for a in anomalies if a.get("severity") == "high"]
    for a in high[:2]:
        label = a.get("label", "unknown period")
        val   = a.get("value", 0)
        if avg and avg != 0:
            pct_spike = abs((val - avg) / avg * 100)
            insights.append(_i(
                T.ANOMALY_NOTE.format(metric=metric, pct=pct_spike, period=label),
                "anomaly", 0.9,
            ))

    return insights


def _category_insights(data, summary, params, _qr=None) -> List[Dict]:
    metric = params.get("metric_column", "metric")
    total  = summary.get("total", 0)
    n_cats = summary.get("categories", len(data))
    insights: List[Dict] = []

    insights.append(_i(
        T.CATEGORY_SUMMARY.format(metric=metric, total=total, n=n_cats),
        "summary", 0.95,
    ))

    if data:
        top      = data[0]
        cat_name = top.get("category", "Unknown")
        cat_val  = top.get("value", 0)
        pct      = (cat_val / total * 100) if total else 0
        insights.append(_i(
            T.TOP_CATEGORY.format(category=cat_name, value=cat_val, pct=pct, metric=metric),
            "top_performer", 0.9,
        ))

    if len(data) > 1 and total:
        conc = detect_category_concentration(data, total, k=3)
        if "gap_pct_to_second" in conc:
            insights.append(_i(
                T.CATEGORY_GAP.format(
                    second=conc["second_name"], gap_pct=conc["gap_pct_to_second"]
                ),
                "summary", 0.8,
            ))
        if len(data) >= 3 and conc.get("pct", 0) > 50:
            insights.append(_i(
                T.CONCENTRATION.format(k=conc["k"], pct=conc["pct"], metric=metric),
                "concentration", 0.85,
            ))

    return insights


def _top_k_insights(data, summary, params, _qr=None) -> List[Dict]:
    metric    = params.get("metric_column", "metric")
    k         = params.get("k", 10)
    direction = params.get("direction", "top")
    total     = summary.get("total", 0)
    insights: List[Dict] = []

    insights.append(_i(
        T.TOP_K_SUMMARY.format(direction=direction.capitalize(), k=k, total=total, metric=metric),
        "summary", 0.95,
    ))

    if data:
        w = data[0]
        insights.append(_i(
            T.TOP_K_WINNER.format(rank=1, item=w["item"], value=w["value"], metric=metric),
            "top_performer", 0.9,
        ))

    # Leader vs field gap
    if len(data) > 1:
        leader_val = data[0]["value"]
        rest_total = sum(d["value"] for d in data[1:])
        rest_avg   = rest_total / (len(data) - 1) if len(data) > 1 else 0
        if rest_avg > 0:
            gap_x = leader_val / rest_avg
            if gap_x > 1.5:
                insights.append(_i(
                    T.TOP_K_GAP.format(gap_x=gap_x),
                    "summary", 0.75,
                ))

    # Concentration of top-3
    if len(data) >= 3 and total:
        conc = detect_category_concentration(
            data, total, value_key="value", name_key="item", k=3
        )
        if conc.get("pct", 0) > 60:
            insights.append(_i(
                T.CONCENTRATION.format(k=conc["k"], pct=conc["pct"], metric=metric),
                "concentration", 0.8,
            ))

    return insights


def _scatter_insights(data, summary, params, _qr=None) -> List[Dict]:
    x_col = params.get("x_column", "X")
    y_col = params.get("y_column", "Y")
    corr  = summary.get("correlation", 0)
    insights: List[Dict] = []

    abs_corr = abs(corr)
    if abs_corr > 0.7:
        tmpl = T.CORR_STRONG_POS if corr > 0 else T.CORR_STRONG_NEG
        insights.append(_i(tmpl.format(corr=corr, x=x_col, y=y_col), "correlation", 0.9))
    elif abs_corr > 0.4:
        tmpl = T.CORR_MOD_POS if corr > 0 else T.CORR_MOD_NEG
        insights.append(_i(tmpl.format(corr=corr, x=x_col, y=y_col), "correlation", 0.75))
    else:
        insights.append(_i(T.CORR_WEAK.format(corr=corr, x=x_col, y=y_col), "correlation", 0.6))

    x_mean = summary.get("x_mean", 0)
    y_mean = summary.get("y_mean", 0)
    insights.append(_i(
        T.SCATTER_STATS.format(x=x_col, x_mean=x_mean, y=y_col, y_mean=y_mean),
        "summary", 0.9,
    ))

    return insights


def _correlation_insights(data, summary, params, query_result=None) -> List[Dict]:
    columns   = (query_result or {}).get("columns") or []
    method    = params.get("method", "pearson")
    n_cols    = summary.get("columns_count", len(columns))
    insights: List[Dict] = []

    insights.append(_i(
        f"Correlation matrix ({method.title()}) computed across {n_cols} numeric columns.",
        "summary", 0.95,
    ))

    # Find strongest positive and negative correlations (excluding self-correlations)
    off_diag = [d for d in data if d.get("x") != d.get("y")]
    if off_diag:
        strongest = max(off_diag, key=lambda d: d.get("value", 0))
        weakest   = min(off_diag, key=lambda d: d.get("value", 0))
        if strongest["value"] >= 0.7:
            insights.append(_i(
                f"Strongest positive pair: {strongest['x']} & {strongest['y']} (r={strongest['value']:.2f})",
                "correlation", 0.9,
            ))
        if weakest["value"] <= -0.5:
            insights.append(_i(
                f"Strongest negative pair: {weakest['x']} & {weakest['y']} (r={weakest['value']:.2f})",
                "correlation", 0.9,
            ))
        # Count strong correlations (|r| >= 0.7, off-diagonal, de-duped)
        strong_pairs = {
            tuple(sorted([d["x"], d["y"]]))
            for d in off_diag if abs(d.get("value", 0)) >= 0.7
        }
        if strong_pairs:
            insights.append(_i(
                f"{len(strong_pairs)} strong relationship{'s' if len(strong_pairs) > 1 else ''} found (|r| ≥ 0.70).",
                "concentration", 0.8,
            ))

    return insights


def _grouped_agg_insights(data, summary, params, _qr=None) -> List[Dict]:
    metric      = params.get("metric_column", "metric")
    primary_dim = params.get("primary_dimension", "primary")
    sec_dim     = params.get("secondary_dimension", "secondary")
    total       = summary.get("total", 0)
    n_primary   = summary.get("primary_count", 0)
    n_secondary = summary.get("secondary_count", 0)
    insights: List[Dict] = []

    insights.append(_i(
        f"{metric} totals {total:,.2f} across {n_primary} {primary_dim} groups × {n_secondary} {sec_dim} sub-groups.",
        "summary", 0.95,
    ))

    if data:
        top = max(data, key=lambda d: d.get("value", 0))
        insights.append(_i(
            f"Highest cell: {top['primary']} / {top['secondary']} = {top['value']:,.2f}",
            "top_performer", 0.9,
        ))

    return insights


def _period_insights(data, summary, params, query_result=None) -> List[Dict]:
    metric   = params.get("metric_column", "metric")
    changes  = (query_result or {}).get("changes") or []
    insights: List[Dict] = []

    n = summary.get("periods_compared", len(data))
    total = summary.get("total", 0)
    insights.append(_i(
        f"{metric} totals {total:,.2f} across {n} compared periods.",
        "summary", 0.95,
    ))

    if changes:
        latest = changes[-1]
        pct = latest["pct_change"]
        direction = "trend_up" if pct > 0 else "trend_down"
        word = "grew" if pct > 0 else "fell"
        insights.append(_i(
            f"{metric} {word} {abs(pct):.1f}% from {latest['from']} to {latest['to']} "
            f"({latest['from_value']:,.2f} -> {latest['to_value']:,.2f}).",
            direction, 0.9,
        ))

        # Biggest single jump across all periods
        if len(changes) > 1:
            biggest = max(changes, key=lambda c: abs(c["pct_change"]))
            if biggest is not latest:
                insights.append(_i(
                    f"Largest move overall: {biggest['from']} -> {biggest['to']} ({biggest['pct_change']:+.1f}%).",
                    "sudden_change", 0.8,
                ))

    return insights


def _distribution_insights(data, summary, params, _qr=None) -> List[Dict]:
    column   = params.get("column", "column")
    insights: List[Dict] = []

    unique = summary.get("unique_values")
    if unique is not None:
        # Pie / categorical mode
        total = summary.get("total_values", len(data))
        insights.append(_i(
            T.DIST_SUMMARY.format(column=column, unique=unique, total=total),
            "distribution", 0.9,
        ))
        most_common       = summary.get("most_common")
        most_common_count = summary.get("most_common_count", 0)
        if most_common and total:
            pct = most_common_count / total * 100
            insights.append(_i(
                T.DIST_DOMINANT.format(value=most_common, pct=pct),
                "top_performer", 0.85,
            ))
    else:
        # Histogram mode
        mean   = summary.get("mean", 0)
        median = summary.get("median", 0)
        min_v  = summary.get("min", 0)
        max_v  = summary.get("max", 0)
        insights.append(_i(
            T.DIST_NUMERIC.format(
                column=column, min_v=min_v, max_v=max_v, mean=mean, median=median
            ),
            "distribution", 0.9,
        ))
        if mean != 0 and abs(mean - median) / abs(mean) > 0.1:
            skew_dir = "right (positive)" if mean > median else "left (negative)"
            gap_pct  = abs(mean - median) / abs(mean) * 100
            insights.append(_i(
                T.DIST_SKEW.format(skew_dir=skew_dir, gap_pct=gap_pct),
                "summary", 0.7,
            ))

    return insights
