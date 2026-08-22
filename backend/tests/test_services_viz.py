"""
Unit tests for the visualization layer: ChartFactory config creation and
ChartBuilder Plotly-spec assembly across every chart type, including the
Day-6 additions (heatmap, grouped bar, period comparison).
"""
import pandas as pd
import pytest

from app.services.analytics.query_executor import QueryExecutor
from app.services.visualization import ChartFactory, ChartBuilder


@pytest.fixture(scope="module")
def qx():
    return QueryExecutor(pd.read_csv("data/samples/ecommerce_sales.csv"))


CASES = {
    "trend_over_time": ({"metric_column": "revenue", "time_column": "date",
                         "time_granularity": "month"}, {"scatter"}),
    "category_comparison": ({"metric_column": "revenue", "category_column": "category"}, {"bar"}),
    "distribution_analysis": ({"column": "category"}, {"pie", "bar"}),
    "top_k_items": ({"metric_column": "revenue", "dimension_column": "product", "k": 3}, {"bar"}),
    "scatter_relationship": ({"x_column": "revenue", "y_column": "quantity"}, {"scatter"}),
    "correlation_analysis": ({"method": "pearson"}, {"heatmap"}),
    "grouped_aggregation": ({"metric_column": "revenue", "primary_dimension": "category",
                             "secondary_dimension": "product"}, {"bar"}),
    "period_over_period": ({"metric_column": "revenue", "time_column": "date",
                            "time_granularity": "month", "num_periods": 3}, {"bar"}),
}


@pytest.mark.parametrize("template,params,expected_types",
                         [(t, v[0], v[1]) for t, v in CASES.items()])
def test_chart_spec_is_valid_plotly(qx, template, params, expected_types):
    qr = qx.execute_query(template, params)
    cfg = ChartFactory.create_chart_config(template, qr, params)
    assert "error" not in cfg
    spec = ChartBuilder.build_chart(cfg)
    assert isinstance(spec, dict)
    assert "data" in spec and "layout" in spec
    assert spec["data"], "expected at least one trace"
    trace_types = {tr.get("type") for tr in spec["data"]}
    assert trace_types & expected_types, f"{template}: {trace_types} !~ {expected_types}"


def test_grouped_bar_emits_multiple_traces(qx):
    params = {"metric_column": "revenue", "primary_dimension": "category",
              "secondary_dimension": "product"}
    qr = qx.execute_query("grouped_aggregation", params)
    cfg = ChartFactory.create_chart_config("grouped_aggregation", qr, params)
    spec = ChartBuilder.build_chart(cfg)
    # one trace per secondary value
    assert len(spec["data"]) == len(qr["secondary_values"])


def test_heatmap_has_z_matrix(qx):
    qr = qx.execute_query("correlation_analysis", {"method": "pearson"})
    cfg = ChartFactory.create_chart_config("correlation_analysis", qr, {})
    spec = ChartBuilder.build_chart(cfg)
    heat = spec["data"][0]
    assert heat["type"] == "heatmap"
    assert "z" in heat and len(heat["z"]) >= 2


def test_chart_factory_propagates_error_on_failed_query(qx):
    failed = {"success": False, "error": "boom"}
    cfg = ChartFactory.create_chart_config("trend_over_time", failed, {})
    assert "error" in cfg


def test_top_k_is_horizontal_bar(qx):
    """Phase-2 checklist: 'top 5 ... by revenue' -> horizontal bar."""
    params = {"metric_column": "revenue", "dimension_column": "product", "k": 5}
    qr = qx.execute_query("top_k_items", params)
    spec = ChartBuilder.build_chart(ChartFactory.create_chart_config("top_k_items", qr, params))
    assert spec["data"][0].get("orientation") == "h"


def test_trend_highlights_anomalies_as_separate_trace():
    """Phase-2 checklist: anomalies visually highlighted on time-series charts."""
    sp = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=12, freq="MS").astype(str),
        "revenue": [100, 110, 105, 115, 120, 118, 5000, 122, 119, 125, 130, 128],
    })
    params = {"metric_column": "revenue", "time_column": "date", "time_granularity": "month"}
    qr = QueryExecutor(sp).execute_query("trend_over_time", params)
    assert len(qr.get("anomalies", [])) >= 1
    spec = ChartBuilder.build_chart(ChartFactory.create_chart_config("trend_over_time", qr, params))
    # A dedicated marker trace overlays the anomalous point(s) on the line.
    assert any(t.get("mode") == "markers" for t in spec["data"])
