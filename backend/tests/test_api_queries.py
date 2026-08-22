"""
Integration tests for the queries API: template listing, executing all 8
templates over HTTP, natural-language endpoint (live engine), query history
recording + re-run, and error handling.
"""
import uuid

API = "/api/v1"

TEMPLATE_PARAMS = {
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


def test_list_templates(client, auth):
    r = client.get(f"{API}/queries/templates")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 8
    types = {t["template_type"] for t in body["templates"]}
    assert {"correlation_analysis", "grouped_aggregation", "period_over_period"} <= types


import pytest


@pytest.mark.parametrize("template,params", list(TEMPLATE_PARAMS.items()))
def test_execute_each_template(client, auth, ecommerce_ds, template, params):
    r = client.post(f"{API}/queries/execute", headers=auth["headers"],
                    json={"template_type": template,
                          "dataset_id": ecommerce_ds["id"], "parameters": params})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["plotly_spec"]["data"]
    assert body["insights"]


def test_execute_invalid_template(client, auth, ecommerce_ds):
    r = client.post(f"{API}/queries/execute", headers=auth["headers"],
                    json={"template_type": "nonsense",
                          "dataset_id": ecommerce_ds["id"], "parameters": {}})
    assert r.status_code == 400


def test_execute_requires_auth(client, ecommerce_ds):
    r = client.post(f"{API}/queries/execute",
                    json={"template_type": "category_comparison",
                          "dataset_id": ecommerce_ds["id"],
                          "parameters": {"metric_column": "revenue", "category_column": "category"}})
    assert r.status_code == 401


def test_execute_missing_dataset(client, auth):
    r = client.post(f"{API}/queries/execute", headers=auth["headers"],
                    json={"template_type": "category_comparison",
                          "dataset_id": 999999,
                          "parameters": {"metric_column": "revenue", "category_column": "category"}})
    assert r.status_code == 404


# ── Natural-language endpoint (live engine: LLM-first w/ keyword fallback) ──────

def test_natural_clear_query(client, auth, ecommerce_ds):
    r = client.post(f"{API}/queries/natural", headers=auth["headers"],
                    json={"query_text": "show revenue trend by month",
                          "dataset_id": ecommerce_ds["id"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "trend_over_time"
    # Either it executed (plotly_spec) or returned detected params ready to run
    assert body.get("plotly_spec") or body.get("detected_parameters")


def test_natural_top_k(client, auth, ecommerce_ds):
    r = client.post(f"{API}/queries/natural", headers=auth["headers"],
                    json={"query_text": "top 5 products by revenue",
                          "dataset_id": ecommerce_ds["id"]})
    assert r.status_code == 200
    assert r.json()["intent"] == "top_k_items"


def test_natural_ambiguous_gets_clarification_keyword(client, auth, ecommerce_ds, monkeypatch):
    # Force the deterministic keyword engine: gibberish must NOT produce a chart.
    from app.services.nlp import query_parser
    monkeypatch.setattr(query_parser, "llm_available", lambda: False)
    r = client.post(f"{API}/queries/natural", headers=auth["headers"],
                    json={"query_text": "asdfgh qwerty zxcvbn",
                          "dataset_id": ecommerce_ds["id"]})
    assert r.status_code == 200
    body = r.json()
    assert body.get("clarification") or not body.get("plotly_spec")


def test_natural_ambiguous_llm_path(client, auth, ecommerce_ds):
    # With the LLM clarification gate in place, gibberish must NOT render a chart
    # whether it goes through the live LLM (returns "unclear") or the keyword
    # fallback. Regression test for the missing-confidence-gate finding.
    r = client.post(f"{API}/queries/natural", headers=auth["headers"],
                    json={"query_text": "asdfgh qwerty zxcvbn",
                          "dataset_id": ecommerce_ds["id"]})
    assert r.status_code == 200
    body = r.json()
    assert body.get("clarification") or not body.get("plotly_spec")


# ── Query history ──────────────────────────────────────────────────────────────

def test_history_records_and_reruns(client, auth):
    # Fresh dataset so history count is deterministic
    with open("data/samples/ecommerce_sales.csv", "rb") as f:
        up = client.post(f"{API}/datasets/", headers=auth["headers"],
                         files={"file": ("ecommerce_sales.csv", f, "text/csv")})
    did = up.json()["id"]

    # Execute two queries
    for tmpl, params in [("category_comparison", TEMPLATE_PARAMS["category_comparison"]),
                         ("top_k_items", TEMPLATE_PARAMS["top_k_items"])]:
        client.post(f"{API}/queries/execute", headers=auth["headers"],
                    json={"template_type": tmpl, "dataset_id": did, "parameters": params})

    h = client.get(f"{API}/datasets/{did}/queries", headers=auth["headers"])
    assert h.status_code == 200
    items = h.json()
    assert len(items) >= 2
    # Newest first
    assert items[0]["template_type"] == "top_k_items"
    assert isinstance(items[0]["parameters"], dict)

    # Re-run the most recent saved query using its stored parameters
    top = items[0]
    rerun = client.post(f"{API}/queries/execute", headers=auth["headers"],
                        json={"template_type": top["template_type"],
                              "dataset_id": did, "parameters": top["parameters"]})
    assert rerun.status_code == 200
    assert rerun.json()["success"] is True


def test_history_delete_item(client, auth, ecommerce_ds):
    client.post(f"{API}/queries/execute", headers=auth["headers"],
                json={"template_type": "category_comparison",
                      "dataset_id": ecommerce_ds["id"],
                      "parameters": TEMPLATE_PARAMS["category_comparison"]})
    items = client.get(f"{API}/datasets/{ecommerce_ds['id']}/queries",
                       headers=auth["headers"]).json()
    hid = items[0]["id"]
    d = client.delete(f"{API}/datasets/{ecommerce_ds['id']}/queries/{hid}",
                      headers=auth["headers"])
    assert d.status_code == 204


# ── CH-04 regression: requested_chart_type must not leak into the executor ────
# (it crashed execute_category_comparison() with an unexpected-kwarg TypeError)

def test_requested_chart_type_pie_executes_and_converts(client, auth, ecommerce_ds):
    r = client.post(f"{API}/queries/execute", headers=auth["headers"],
                    json={"template_type": "category_comparison",
                          "dataset_id": ecommerce_ds["id"],
                          "parameters": {"metric_column": "revenue",
                                         "category_column": "category",
                                         "requested_chart_type": "pie"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body.get("message")
    assert body["chart_config"]["chart_type"] == "pie"
    assert body["plotly_spec"]["data"][0]["type"] == "pie"


def test_requested_chart_type_stacked_bar_executes(client, auth, ecommerce_ds):
    r = client.post(f"{API}/queries/execute", headers=auth["headers"],
                    json={"template_type": "category_comparison",
                          "dataset_id": ecommerce_ds["id"],
                          "parameters": {"metric_column": "revenue",
                                         "category_column": "category",
                                         "requested_chart_type": "stacked_bar"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["plotly_spec"]["layout"].get("barmode") == "stack"
