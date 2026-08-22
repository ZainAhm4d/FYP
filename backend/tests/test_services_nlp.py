"""
Unit tests for the hybrid NLP engine (keyword/offline path).

The LLM path is force-disabled here so results are deterministic and offline;
the live LLM path is smoke-tested separately in the API tests.
"""
import pytest

from app.services.nlp.intent_classifier import classify_intent, get_nlp_mode
from app.services.nlp.entity_extractor import extract_entities
from app.services.nlp import query_parser

COLUMNS = [
    {"name": "date", "category": "date"},
    {"name": "revenue", "category": "metric"},
    {"name": "quantity", "category": "metric"},
    {"name": "category", "category": "dimension"},
    {"name": "product", "category": "dimension"},
]


@pytest.fixture(autouse=True)
def _force_keyword(monkeypatch):
    """Disable the LLM so the deterministic keyword engine is exercised."""
    monkeypatch.setattr(query_parser, "llm_available", lambda: False)


@pytest.fixture
def keyword_mode(monkeypatch):
    """Pin the intent classifier to keyword mode regardless of whether
    sentence-transformers is installed, so mode/confidence assertions are
    environment-independent. See TI-03 in CLEANING_PIPELINE.md.
    """
    from app.services.nlp import intent_classifier as ic
    monkeypatch.setattr(ic._classifier, "_loaded", True)
    monkeypatch.setattr(ic._classifier, "_mode", "keyword")
    monkeypatch.setattr(ic._classifier, "_model", None)
    yield


# ── Intent classification ──────────────────────────────────────────────────────

@pytest.mark.parametrize("query,expected", [
    ("show sales trend by month", "trend_over_time"),
    ("revenue over time", "trend_over_time"),
    ("top 5 products by revenue", "top_k_items"),
    ("compare revenue by category", "category_comparison"),
    ("distribution of prices", "distribution_analysis"),
    ("correlation between price and quantity", "scatter_relationship"),
])
def test_intent_classification(query, expected):
    intent, conf = classify_intent(query)
    assert intent == expected, f"{query!r} -> {intent} (conf={conf})"
    assert 0.0 <= conf <= 1.0


def test_gibberish_low_confidence(keyword_mode):
    intent, conf = classify_intent("asdfgh qwerty zxcvbn")
    assert conf < 0.05  # below the keyword clarification threshold


# ── Entity extraction ──────────────────────────────────────────────────────────

def test_entity_extraction_top_k():
    e = extract_entities("top 5 products by revenue", COLUMNS, "top_k_items")
    p = e["parameters"]
    assert p["metric_column"] == "revenue"
    assert p["dimension_column"] == "product"
    assert p["k"] == 5
    assert p["direction"] == "top"


def test_entity_extraction_trend_maps_time_and_metric():
    e = extract_entities("show revenue trend by month", COLUMNS, "trend_over_time")
    p = e["parameters"]
    assert p.get("metric_column") == "revenue"
    assert p.get("time_column") == "date"


# ── Full parser orchestration ──────────────────────────────────────────────────

def test_parser_ready_for_clear_query():
    res = query_parser.parse_natural_query("show revenue trend by month", COLUMNS)
    assert res["intent"] == "trend_over_time"
    assert res["ready"] is True
    assert res["clarification"] is None
    assert res["parameters"].get("metric_column") == "revenue"


def test_parser_clarifies_on_gibberish():
    res = query_parser.parse_natural_query("asdfgh qwerty zxcvbn", COLUMNS)
    assert res["ready"] is False
    assert res["clarification"] is not None


def test_parser_reports_keyword_mode(keyword_mode):
    res = query_parser.parse_natural_query("top 3 products by revenue", COLUMNS)
    assert res["nlp_mode"] == "keyword"
    assert res["parameters"].get("k") == 3


def test_parser_reports_embeddings_mode_when_available(monkeypatch):
    """Counterpart to the keyword-mode test: when sentence-transformers is
    installed, a clear query should classify via embeddings. Skipped in
    environments without the optional dependency. See TI-03."""
    pytest.importorskip("sentence_transformers")
    from app.services.nlp import intent_classifier as ic
    # Ensure the classifier actually loaded in embeddings mode in this env.
    if ic.get_nlp_mode() != "embeddings":
        pytest.skip("classifier not in embeddings mode in this environment")
    res = query_parser.parse_natural_query("show revenue trend by month", COLUMNS)
    assert res["nlp_mode"] == "embeddings"


# ── CH-04: chart-type requests, multi-part and under-specified guards ─────────

def test_ch04_pie_request_sets_chart_type_not_intent(keyword_mode):
    res = query_parser.parse_natural_query("make a pie chart of revenue by category", COLUMNS)
    assert res["intent"] == "category_comparison"
    assert res["parameters"].get("requested_chart_type") == "pie"


def test_ch04_stacked_horizontal_request(keyword_mode):
    ct, stripped = query_parser.extract_requested_chart_type(
        "show revenue by category as a stacked horizontal bar chart")
    assert ct == "stacked_horizontal"
    assert "bar chart" not in stripped


def test_ch04_multipart_query_clarifies(keyword_mode):
    res = query_parser.parse_natural_query(
        "show revenue trend by month and also top 5 products by revenue", COLUMNS)
    assert res["ready"] is False
    assert res["clarification"] is not None


def test_ch04_underspecified_query_clarifies(keyword_mode):
    # names an analysis but no real column ("figures" matches nothing)
    res = query_parser.parse_natural_query("compare the figures", COLUMNS)
    assert res["ready"] is False
    assert res["clarification"] is not None
