"""
Unit tests for the analytics layer: all 8 query executors, anomaly detection,
and insight narrative generation. Uses the bundled ecommerce sample plus
synthetic frames for edge cases.
"""
import pandas as pd
import pytest

from app.services.analytics.query_executor import QueryExecutor
from app.services.analytics.anomaly_detection import detect_anomalies
from app.services.insights import generate_insights


@pytest.fixture(scope="module")
def ecom():
    return pd.read_csv("data/samples/ecommerce_sales.csv")


@pytest.fixture(scope="module")
def qx(ecom):
    return QueryExecutor(ecom)


# ── The 8 templates all execute successfully ───────────────────────────────────

ALL_QUERIES = {
    "trend_over_time": {"metric_column": "revenue", "time_column": "date",
                        "aggregation": "sum", "time_granularity": "month"},
    "category_comparison": {"metric_column": "revenue", "category_column": "category"},
    "distribution_analysis": {"column": "category"},
    "top_k_items": {"metric_column": "revenue", "dimension_column": "product", "k": 3},
    "scatter_relationship": {"x_column": "revenue", "y_column": "quantity"},
    "correlation_analysis": {"method": "pearson"},
    "grouped_aggregation": {"metric_column": "revenue", "primary_dimension": "category",
                            "secondary_dimension": "product"},
    "period_over_period": {"metric_column": "revenue", "time_column": "date",
                           "time_granularity": "month", "num_periods": 3},
}


@pytest.mark.parametrize("template,params", list(ALL_QUERIES.items()))
def test_all_templates_execute(qx, template, params):
    res = qx.execute_query(template, params)
    assert res["success"] is True, res.get("error")
    assert isinstance(res["data"], list)
    assert res["data"], "expected non-empty data"


# ── Numerical correctness checks ───────────────────────────────────────────────

def test_category_comparison_totals_match_pandas(ecom, qx):
    res = qx.execute_query("category_comparison",
                           {"metric_column": "revenue", "category_column": "category"})
    by_cat = {d["category"]: d["value"] for d in res["data"]}
    expected = ecom.groupby("category")["revenue"].sum().to_dict()
    for cat, val in expected.items():
        assert by_cat[cat] == pytest.approx(val, rel=1e-6)


def test_top_k_respects_k_and_order(qx):
    res = qx.execute_query("top_k_items",
                           {"metric_column": "revenue", "dimension_column": "product", "k": 3})
    assert len(res["data"]) <= 3
    values = [d["value"] for d in res["data"]]
    assert values == sorted(values, reverse=True)


def test_correlation_diagonal_is_one(qx):
    res = qx.execute_query("correlation_analysis", {"method": "pearson"})
    diag = [d for d in res["data"] if d["x"] == d["y"]]
    assert all(d["value"] == pytest.approx(1.0, abs=1e-6) for d in diag)


def test_correlation_needs_two_numeric_columns():
    df = pd.DataFrame({"only": [1, 2, 3], "label": ["a", "b", "c"]})
    res = QueryExecutor(df).execute_query("correlation_analysis", {"method": "pearson"})
    assert res["success"] is False


def test_grouped_aggregation_secondary_values(qx):
    res = qx.execute_query("grouped_aggregation",
                           {"metric_column": "revenue", "primary_dimension": "category",
                            "secondary_dimension": "product"})
    assert res["secondary_values"]
    for row in res["data"]:
        assert {"primary", "secondary", "value"} <= row.keys()


def test_period_over_period_changes(qx):
    res = qx.execute_query("period_over_period",
                           {"metric_column": "revenue", "time_column": "date",
                            "time_granularity": "month", "num_periods": 3})
    assert "changes" in res
    for c in res["changes"]:
        assert "pct_change" in c


# ── Error handling ─────────────────────────────────────────────────────────────

def test_unknown_template_returns_error(qx):
    res = qx.execute_query("does_not_exist", {})
    assert res["success"] is False


def test_missing_required_param_is_handled(qx):
    # category_comparison without metric_column must fail gracefully (not raise).
    # Regression test for the execute_query try/finally-without-except bug.
    res = qx.execute_query("category_comparison", {"category_column": "category"})
    assert res["success"] is False
    assert "parameter" in res["error"].lower()


def test_filter_to_empty_returns_error(qx):
    res = qx.execute_query("category_comparison", {
        "metric_column": "revenue", "category_column": "category",
        "filters": [{"column": "category", "value": "NoSuchCategory"}],
    })
    assert res["success"] is False


# ── Anomaly detection ──────────────────────────────────────────────────────────

def test_zscore_flags_single_spike():
    df = pd.DataFrame({"revenue": [100, 110, 105, 900, 108, 112, 107]})
    anomalies = detect_anomalies(df, column="revenue", method="zscore", threshold=2.0)
    assert len(anomalies) >= 1
    assert any(a.get("value") == 900 for a in anomalies)
    assert all("severity" in a for a in anomalies)


def test_zscore_no_anomaly_on_flat_series():
    df = pd.DataFrame({"revenue": [100, 101, 99, 100, 100, 101, 99]})
    anomalies = detect_anomalies(df, column="revenue", method="zscore", threshold=3.0)
    assert anomalies == []


def test_isolation_forest_multivariate():
    df = pd.DataFrame({
        "a": [1, 2, 1, 2, 1, 2, 50],
        "b": [1, 2, 1, 2, 1, 2, 60],
    })
    anomalies = detect_anomalies(df, method="isolation_forest", contamination=0.2)
    assert isinstance(anomalies, list)


# ── Insight narratives for all templates ───────────────────────────────────────

@pytest.mark.parametrize("template,params", list(ALL_QUERIES.items()))
def test_insights_generated_for_every_template(qx, template, params):
    res = qx.execute_query(template, params)
    insights = generate_insights(template_type=template, query_result=res, parameters=params)
    assert isinstance(insights, list)
    assert len(insights) >= 1
    for ins in insights:
        assert "text" in ins and ins["text"]
        assert "type" in ins
        assert 0.0 <= ins["confidence"] <= 1.0


def test_insights_empty_data():
    insights = generate_insights("trend_over_time", {"data": [], "summary": {}}, {})
    assert len(insights) == 1
    assert "No data" in insights[0]["text"]
