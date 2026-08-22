"""
Query Parser — orchestrates intent classification → entity extraction
to produce a ready-to-execute parameter set (or a clarification prompt).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .entity_extractor import extract_entities
from .intent_classifier import classify_intent, get_nlp_mode
from .llm_parser import parse_with_llm, llm_available
from .synonym_manager import score_intent_keywords

logger = logging.getLogger(__name__)

# ── CH-04: explicit chart-style requests ──────────────────────────────────────
# "make a pie chart of revenue by region" must set the chart type WITHOUT
# influencing the intent (pie/histogram words are also distribution keywords).

_CHART_WORD_MAP = {
    "pie": "pie", "donut": "pie", "doughnut": "pie",
    "line": "line", "area": "area", "scatter": "scatter",
    "bar": "bar", "column": "bar",
}

_CHART_TYPE_RE = re.compile(
    r"""(?:\bmake\b|\bshow\b|\bdraw\b|\bplot\b|\bbuild\b|\bcreate\b|\bas\b|\bto\b|\binto\b|\bbe\b)?
        \s*(?:a|an|the)?\s*
        (?P<mods>(?:stacked|horizontal)\s+)*
        (?P<word>pie|donut|doughnut|line|area|scatter|bar|column)
        \s*(?:chart|graph|plot)\b""",
    re.IGNORECASE | re.VERBOSE,
)
# bare "as a pie" / "make it stacked" style (no trailing 'chart' word)
_CHART_TYPE_BARE_RE = re.compile(
    r"\b(?:as|into|make it|make this)\s+(?:a|an)?\s*"
    r"(?P<mods>(?:stacked|horizontal)\s+)*"
    r"(?P<word>pie|donut|doughnut|line|area|scatter|bar|column)\b",
    re.IGNORECASE,
)


def extract_requested_chart_type(query_text: str) -> Tuple[Optional[str], str]:
    """Return (requested_chart_type | None, query text with the phrase removed).

    Stripping the matched phrase before intent scoring stops chart-style words
    ("pie chart") from flipping the intent to distribution_analysis.
    """
    m = _CHART_TYPE_RE.search(query_text) or _CHART_TYPE_BARE_RE.search(query_text)
    if not m:
        return None, query_text
    base = _CHART_WORD_MAP[m.group("word").lower()]
    mods = (m.group("mods") or "").lower()
    stacked = "stacked" in mods or re.search(r"\bstack(?:ed)?\b", query_text, re.I) is not None
    horizontal = "horizontal" in mods
    if base == "bar" and stacked and horizontal:
        chart = "stacked_horizontal"
    elif base == "bar" and stacked:
        chart = "stacked_bar"
    elif base == "bar" and horizontal:
        chart = "horizontal_bar"
    else:
        chart = base
    stripped = (query_text[:m.start()] + " " + query_text[m.end():]).strip()
    # Keep enough text for intent scoring; if the whole query WAS the chart
    # request ("pie chart"), fall back to the original text.
    return chart, (stripped if len(stripped.split()) >= 2 else query_text)


# CH-04: coordinating patterns that suggest two different asks in one sentence
_MULTI_PART_RE = re.compile(r"\band\s+also\b|\bas\s+well\s+as\b|\bplus\b|;", re.IGNORECASE)

# Below this cosine-similarity confidence we ask the user to rephrase
# (only applies in embeddings mode — keyword mode always gives an answer).
# Embeddings mode: reject if cosine similarity is below this.
EMBEDDINGS_CONFIDENCE_THRESHOLD = 0.35

# Keyword mode: reject if normalised keyword score is below this.
# 0.0 means NO analytical keyword was found at all (e.g. "what is abc revenue").
# We use a small epsilon (> 0) so that a single ambiguous keyword match also
# triggers clarification instead of blindly executing.
KEYWORD_CONFIDENCE_THRESHOLD = 0.05

_CLARIFY_REPHRASE = (
    "I'm not sure what kind of analysis you'd like. "
    "Could you be more specific? For example:\n"
    "- 'show sales trend by month' - trend over time\n"
    "- 'compare revenue by category' - category comparison\n"
    "- 'top 5 products by sales' - ranking\n"
    "- 'distribution of prices' - frequency breakdown\n"
    "- 'correlation between price and quantity' - scatter plot"
)


def parse_natural_query(
    query_text: str,
    columns: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Parse a natural-language query into a structured request object.

    Args:
        query_text: The user's plain-English question.
        columns:    Column metadata list from the dataset
                    ({name, category, dtype, unique_count, null_count}).

    Returns:
        {
            "intent":      str,               # template type name
            "confidence":  float,             # 0..1
            "parameters":  Dict[str, Any],    # ready to pass to QueryExecutor
            "clarification": str | None,      # set when user input is ambiguous
            "ready":       bool,              # True when parameters are complete
            "nlp_mode":    str,               # "embeddings" or "keyword"
        }
    """
    # Step 0 — CH-04: pull out an explicit chart-style request up front so the
    # style words can't distort intent classification.
    requested_chart, intent_text = extract_requested_chart_type(query_text)

    # Step 1 — Try LLM parser first if API key is configured
    if llm_available():
        llm_result = parse_with_llm(query_text, columns)
        if llm_result is not None:
            logger.info(
                "NLP parse (LLM) | query=%r | intent=%s | ready=%s",
                query_text,
                llm_result.get("intent"),
                llm_result.get("ready"),
            )
            # Regex extraction backstops the model if it ignored the style ask
            if requested_chart and llm_result.get("parameters") is not None:
                llm_result["parameters"].setdefault("requested_chart_type", requested_chart)
            return llm_result
        logger.warning("LLM parse failed — falling back to keyword NLP")

    # Step 2 — Keyword / embeddings fallback (intent scored on the stripped text)
    intent, confidence = classify_intent(intent_text)
    nlp_mode = get_nlp_mode()

    # CH-04: multi-part guard — two near-tied intents joined by a coordinating
    # phrase is almost always two different questions in one sentence.
    if nlp_mode == "keyword" and _MULTI_PART_RE.search(query_text):
        scores = score_intent_keywords(intent_text.lower())
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        if len(ranked) >= 2 and ranked[0][1] > 0 and ranked[1][1] >= ranked[0][1] * 0.85:
            return {
                "intent":        "unclear",
                "confidence":    confidence,
                "parameters":    {},
                "clarification": (
                    "That looks like two different questions in one — I can chart "
                    f"one analysis at a time. Did you mean a {ranked[0][0].replace('_', ' ')} "
                    f"or a {ranked[1][0].replace('_', ' ')}? Try asking them separately."
                ),
                "ready":         False,
                "nlp_mode":      nlp_mode,
            }

    logger.info(
        "NLP parse | query=%r | intent=%s | conf=%.3f | mode=%s",
        query_text,
        intent,
        confidence,
        nlp_mode,
    )

    # Reject when confidence is too low regardless of mode.
    threshold = (
        EMBEDDINGS_CONFIDENCE_THRESHOLD
        if nlp_mode == "embeddings"
        else KEYWORD_CONFIDENCE_THRESHOLD
    )
    if confidence < threshold:
        return {
            "intent":        intent,
            "confidence":    confidence,
            "parameters":    {},
            "clarification": _CLARIFY_REPHRASE,
            "ready":         False,
            "nlp_mode":      nlp_mode,
        }

    # Step 3 — Extract entities / map to parameters (chart-style phrase removed)
    extraction = extract_entities(intent_text, columns, intent)
    parameters        = extraction["parameters"]
    entity_clarify    = extraction.get("clarification")

    if requested_chart and parameters is not None:
        parameters["requested_chart_type"] = requested_chart

    clarification: Optional[str] = entity_clarify
    ready = clarification is None and bool(parameters)

    # CH-04: under-specified guard — every column was filled by defaults, none
    # by the user's words. Ask instead of charting a guess.
    if ready and not extraction.get("had_column_evidence", True):
        clarification = (
            "I picked columns by default because your question didn't name any. "
            "Which column should I analyse? (e.g. 'revenue trend by month', "
            "'top products by quantity')"
        )
        ready = False

    return {
        "intent":        intent,
        "confidence":    confidence,
        "parameters":    parameters,
        "clarification": clarification,
        "ready":         ready,
        "nlp_mode":      nlp_mode,
    }
