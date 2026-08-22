"""
Entity Extractor — maps natural-language query tokens to dataset column names
and extracts structured parameter values (aggregation, K, direction, granularity).

Uses spaCy (en_core_web_sm) for lemmatisation when available;
falls back to a simple regex tokeniser if spaCy is not installed.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from .synonym_manager import (
    expand_with_synonyms,
    extract_k_value,
    resolve_aggregation,
    resolve_direction,
    resolve_granularity,
)

logger = logging.getLogger(__name__)

# Optional spaCy import
try:
    import spacy as _spacy_module

    _nlp = _spacy_module.load("en_core_web_sm")
    SPACY_AVAILABLE = True
    logger.info("EntityExtractor: spaCy en_core_web_sm loaded")
except (ImportError, OSError):
    _nlp = None
    SPACY_AVAILABLE = False
    logger.warning(
        "EntityExtractor: spaCy not available — using regex tokeniser. "
        "Install: pip install spacy && python -m spacy download en_core_web_sm"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    """Case-insensitive SequenceMatcher ratio (0..1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _column_match_score(tokens: List[str], column_name: str) -> float:
    """
    Score how well a set of (expanded) query tokens match a column name.
    Returns 0..1; higher = better.
    """
    col_lower = column_name.lower().replace("_", " ")
    col_words = col_lower.split()

    best = 0.0
    for token in tokens:
        # Exact substring of the full column name
        if token == col_lower:
            return 1.0
        if token in col_lower:
            best = max(best, 0.90)
        # Word-level exact match
        if token in col_words:
            best = max(best, 0.95)
        # Fuzzy against each column word
        for cw in col_words:
            sim = _similarity(token, cw)
            best = max(best, sim * 0.85)  # slight discount for fuzzy

    return best


def _best_column(
    tokens: List[str],
    candidates: List[Dict[str, Any]],
    min_score: float = 0.45,
) -> Optional[str]:
    """Return the column with the highest match score, or None if below threshold."""
    if not candidates:
        return None
    scored = [
        (col["name"], _column_match_score(tokens, col["name"]))
        for col in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    name, score = scored[0]
    return name if score >= min_score else None


def _extract_by_clause(query_lower: str, candidates: List[Dict[str, Any]]) -> Optional[str]:
    """
    Extract an explicit 'by <X>' specification and match it against candidates.
    'show top products by revenue' → tries to match 'revenue' against candidates.
    Takes priority over fuzzy token matching since it is an unambiguous user signal.
    """
    # Match the last 'by <word>' phrase — users put the metric at the end
    matches = list(re.finditer(r'\bby\s+(\w+(?:\s+\w+)?)', query_lower))
    if not matches:
        return None
    for m in reversed(matches):
        by_token = m.group(1).strip().split()[0]  # first word only
        col = _best_column([by_token], candidates, min_score=0.50)
        if col:
            return col
    return None


def _extract_top_subject(query_lower: str, candidates: List[Dict[str, Any]]) -> Optional[str]:
    """
    Extract the noun being ranked in 'top/best <adj*> <noun> in/by/for ...' patterns.

    Strategy: the ranked subject is the word that appears JUST BEFORE a
    limiting preposition ('in', 'by', 'for', 'from', 'of', 'per').
    e.g. 'top selling product in north region by revenue'
                              ^^^^^^^  ← before 'in'  → 'product'

    Falls back to the first noun after the ranking keyword if no preposition found.
    """
    _RANK_WORDS = r'(?:top|best|highest|lowest|most|least|worst)'
    _PREP = r'(?:in|by|for|from|of|per|with|within)'
    _FILLER = {"the", "a", "an", "by", "in", "of", "for", "and", "or", "is", "are"}

    # Primary: word right before a preposition inside a ranking phrase
    m = re.search(
        rf'\b{_RANK_WORDS}\s+(?:\w+\s+){{0,4}}?(\w{{3,}})\s+{_PREP}\b',
        query_lower,
    )
    if m:
        subject = m.group(1)
        if subject not in _FILLER:
            col = _best_column([subject], candidates, min_score=0.45)
            if col:
                return col

    # Fallback: first sufficiently long word after the ranking keyword
    m2 = re.search(rf'\b{_RANK_WORDS}\s+(?:\w+\s+){{0,2}}?(\w{{4,}})', query_lower)
    if m2:
        subject = m2.group(1)
        if subject not in _FILLER:
            col = _best_column([subject], candidates, min_score=0.45)
            if col:
                return col

    return None


def _extract_filters(
    query_lower: str,
    dimensions: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """
    Extract WHERE-style filters from natural-language phrases:
      'in north region'  → [{column: 'Region', value: 'North'}]
      'for west area'    → [{column: 'Area',   value: 'West'}]

    Strategy: look for 'in/for/from/within/at <value_word> <column_word>'
    and match column_word against dimension column names.
    """
    # Build a lookup: lowercase column word → canonical column name
    dim_lookup: Dict[str, str] = {}
    for col in dimensions:
        col_lower = col["name"].lower()
        dim_lookup[col_lower] = col["name"]
        for word in re.split(r"[\s_]+", col_lower):
            if len(word) >= 3:
                dim_lookup[word] = col["name"]

    filters: List[Dict[str, str]] = []
    seen: set = set()

    for m in re.finditer(
        r'\b(?:in|for|from|within|at)\s+(\w+)\s+(\w+)', query_lower
    ):
        val_token, col_token = m.group(1), m.group(2)
        if col_token in dim_lookup:
            col_name = dim_lookup[col_token]
            key = (col_name, val_token.lower())
            if key not in seen:
                seen.add(key)
                filters.append({"column": col_name, "value": val_token.title()})

    return filters


def _resolve_column(
    tokens: List[str],
    candidates: List[Dict[str, Any]],
    missing_msg: str,
    missing: List[str],
    min_score: float = 0.45,
) -> Optional[str]:
    """
    Resolve a required column with a smart auto-fallback strategy:

    1. Try token-based fuzzy matching first (best explicit match).
    2. If no explicit match AND only one candidate exists → use it automatically.
       The user can't pick anything else anyway, so asking is pointless.
    3. If no match AND multiple candidates → add missing_msg and return None
       so a clarification prompt is built.
    """
    col = _best_column(tokens, candidates, min_score)
    if col is not None:
        return col

    if len(candidates) == 1:
        # Only one option — use it without asking
        return candidates[0]["name"]

    # Multiple options, none clearly mentioned — need clarification
    if missing_msg:
        missing.append(missing_msg)
    return None


def _tokenise(text: str) -> List[str]:
    """Simple regex tokeniser — splits on non-alphanumeric chars."""
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _tokenise_spacy(text: str) -> List[str]:
    """Lemmatise with spaCy; drop stop-words and punctuation."""
    doc = _nlp(text)
    return [
        tok.lemma_.lower()
        for tok in doc
        if not tok.is_stop and not tok.is_punct and tok.is_alpha
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_entities(
    query_text: str,
    columns: List[Dict[str, Any]],
    intent: str,
) -> Dict[str, Any]:
    """
    Extract structured query parameters from a plain-English question.

    Args:
        query_text: The user's natural-language question.
        columns:    Column metadata list from the dataset; each entry is a dict
                    with at least {name, category} where category is one of
                    'metric', 'dimension', 'date'.
        intent:     Classified template type string (e.g. 'trend_over_time').

    Returns:
        {
            "parameters":   Dict matching the QueryExecutor argument names,
            "clarification": str | None   (None when all required params found),
            "missing":       List[str]    (human-readable descriptions of gaps),
        }
    """
    query_lower = query_text.lower()

    # Tokenise
    base_tokens = _tokenise_spacy(query_text) if SPACY_AVAILABLE else _tokenise(query_lower)

    # Expand with business synonyms so "sales" → also try matching "revenue" column
    tokens = expand_with_synonyms(base_tokens)

    # Partition columns by type
    metrics    = [c for c in columns if c["category"] == "metric"]
    dimensions = [c for c in columns if c["category"] == "dimension"]
    date_cols  = [c for c in columns if c["category"] == "date"]

    params: Dict[str, Any] = {}
    missing: List[str] = []

    # ------------------------------------------------------------------
    # Pre-extraction: explicit signals that override fuzzy matching
    # ------------------------------------------------------------------
    # "by revenue" → user explicitly named the metric; use it first.
    explicit_metric = _extract_by_clause(query_lower, metrics)
    # "in north region" → WHERE-clause filter (extract before subject so we can exclude filter cols).
    filters = _extract_filters(query_lower, dimensions)
    if filters:
        params["filters"] = filters

    # Columns already used as filters must not also become the dimension to rank/group by.
    filter_col_names = {f["column"] for f in filters}
    rankable_dims = [d for d in dimensions if d["name"] not in filter_col_names]

    # "top selling product" → the noun being ranked; search only in rankable dims.
    explicit_subject = _extract_top_subject(query_lower, rankable_dims)

    if intent == "trend_over_time":
        metric = (
            explicit_metric
            or _resolve_column(
                tokens, metrics,
                "which metric to track (e.g. revenue, sales, quantity)",
                missing,
            )
        )
        time_col = _resolve_column(
            tokens, date_cols,
            "which date / time column to use",
            missing,
        )

        if metric:
            params["metric_column"] = metric
        if time_col:
            params["time_column"] = time_col

        params["aggregation"]      = resolve_aggregation(query_lower)
        params["time_granularity"] = resolve_granularity(query_lower)

    elif intent == "category_comparison":
        metric = (
            explicit_metric
            or _resolve_column(
                tokens, metrics,
                "which numeric metric to compare (e.g. revenue, quantity)",
                missing,
            )
        )
        category = (
            explicit_subject
            or _resolve_column(
                tokens, rankable_dims,
                "which category / dimension to group by (e.g. product, region)",
                missing,
            )
        )

        if metric:
            params["metric_column"] = metric
        if category:
            params["category_column"] = category

        params["aggregation"] = resolve_aggregation(query_lower)
        params["sort_order"]  = "desc"

    elif intent == "distribution_analysis":
        all_cols = metrics + dimensions
        col = _resolve_column(
            tokens, all_cols,
            "which column to analyse the distribution of",
            missing,
        )
        if col:
            params["column"] = col

        params["chart_preference"] = "auto"
        params["bins"]             = 10

    elif intent == "top_k_items":
        metric = (
            explicit_metric
            or _resolve_column(
                tokens, metrics,
                "which metric to rank by (e.g. revenue, sales, quantity)" if len(metrics) > 1 else None,
                missing,
            )
        )
        dimension = (
            explicit_subject
            or _resolve_column(
                tokens, rankable_dims,
                "which items to rank (e.g. products, employees)" if len(rankable_dims) > 1 else None,
                missing,
            )
        )

        if metric:
            params["metric_column"] = metric
        if dimension:
            params["dimension_column"] = dimension

        params["k"]           = extract_k_value(query_lower)
        params["direction"]   = resolve_direction(query_lower)
        params["aggregation"] = resolve_aggregation(query_lower)

    elif intent == "scatter_relationship":
        if len(metrics) >= 2:
            ranked = sorted(
                metrics,
                key=lambda c: _column_match_score(tokens, c["name"]),
                reverse=True,
            )
            params["x_column"] = ranked[0]["name"]
            params["y_column"] = ranked[1]["name"]
        elif len(metrics) == 1:
            params["x_column"] = metrics[0]["name"]
            missing.append("a second numeric column for the Y-axis")
        else:
            missing.append("two numeric columns to compare")

    # ------------------------------------------------------------------
    # Build clarification prompt
    # ------------------------------------------------------------------
    clarification: Optional[str] = None
    if missing:
        clarification = "Could you clarify: " + "; and ".join(missing) + "?"

    # CH-04: did ANY resolved column come from actual words in the query, or
    # were they all single-candidate defaults? Zero evidence = we'd be charting
    # a guess — the parser turns that into a clarification instead.
    _col_keys = ("metric_column", "category_column", "dimension_column",
                 "time_column", "column", "x_column", "y_column")
    resolved = [v for k, v in params.items() if k in _col_keys and isinstance(v, str)]
    had_column_evidence = any(
        _column_match_score(tokens, c) >= 0.45 for c in resolved
    ) if resolved else False

    return {
        "parameters":    params,
        "clarification": clarification,
        "missing":       missing,
        "had_column_evidence": had_column_evidence,
    }
