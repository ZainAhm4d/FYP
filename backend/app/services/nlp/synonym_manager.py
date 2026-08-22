"""
Synonym and keyword manager for the NLP query engine.
Maps business terms, aggregation words, and time expressions to
structured values used by the entity extractor and intent classifier.
"""
from typing import Dict, List
import re

# Per-intent keyword sets used for keyword-fallback classification.
# Multi-word phrases score higher (weighted 2x) than single words.
INTENT_KEYWORDS: Dict[str, List[str]] = {
    "trend_over_time": [
        "trend", "over time", "by month", "by year", "by quarter", "by week", "by day",
        "monthly", "yearly", "quarterly", "weekly", "daily", "timeline", "time series",
        "history", "growth", "progress", "change over", "over the", "across time",
        "time period", "tracking", "track", "over months", "over years", "per month",
        "per year", "per quarter", "each month", "each year",
    ],
    "category_comparison": [
        "compare", "comparison", "by category", "per category", "across categories",
        "each category", "group by", "breakdown by", "versus", "vs", "different",
        "between categories", "by region", "by department", "by segment", "by type",
        "per region", "per department", "across regions",
    ],
    "distribution_analysis": [
        "distribution", "spread", "breakdown", "proportion", "percentage", "share",
        "how many", "frequency", "histogram", "pie chart", "composition",
        "what percentage", "what proportion", "how is", "how are",
    ],
    "top_k_items": [
        "top", "bottom", "best", "worst", "highest", "lowest", "ranking", "rank",
        "most", "least", "leading", "trailing", "best performing", "worst performing",
        "greatest", "smallest", "top 5", "top 10", "top 3",
    ],
    "scatter_relationship": [
        "correlation", "relationship", "relate", "scatter", "between", "versus",
        "vs", "affect", "impact", "influence", "association", "correlated",
        "relationship between", "how does", "does price",
    ],
}

# Business-domain synonym groups.
# Keys are canonical column-name fragments; values are common query synonyms.
# The entity extractor uses this to expand query tokens before fuzzy-matching
# against actual column names (e.g. "sales" → try matching "revenue" column).
BUSINESS_SYNONYMS: Dict[str, List[str]] = {
    "revenue": ["sales", "income", "earnings", "turnover", "receipts", "money"],
    "profit": ["margin", "net income", "gain", "profitability"],
    "quantity": ["qty", "units", "volume", "sold", "number sold", "selling", "sell", "purchases"],
    "price": ["cost", "rate", "value", "fee", "charge", "unit price"],
    "salary": ["compensation", "pay", "wage", "remuneration"],
    "age": ["years old", "tenure"],
    "date": ["time", "period", "when", "day", "month", "year"],
    "product": ["item", "sku", "goods", "merchandise"],
    "customer": ["client", "buyer", "consumer", "user"],
    "region": ["area", "zone", "territory", "location", "place"],
    "category": ["type", "segment", "group", "class"],
    "department": ["dept", "division", "team", "unit"],
    "employee": ["staff", "worker", "person", "member"],
    "order": ["purchase", "transaction", "sale"],
    "count": ["number", "total count", "frequency"],
}

AGGREGATION_MAP: Dict[str, str] = {
    "total": "sum",
    "sum": "sum",
    "combined": "sum",
    "overall": "sum",
    "cumulative": "sum",
    "average": "mean",
    "avg": "mean",
    "mean": "mean",
    "typical": "mean",
    "count": "count",
    "frequency": "count",
    "maximum": "max",
    "peak": "max",
    "minimum": "min",
    "floor": "min",
}

DIRECTION_MAP: Dict[str, str] = {
    "top": "top",
    "best": "top",
    "highest": "top",
    "most": "top",
    "leading": "top",
    "greatest": "top",
    "maximum": "top",
    "bottom": "bottom",
    "worst": "bottom",
    "lowest": "bottom",
    "least": "bottom",
    "minimum": "bottom",
    "smallest": "bottom",
    "trailing": "bottom",
}

GRANULARITY_MAP: Dict[str, str] = {
    "daily": "day",
    "by day": "day",
    "each day": "day",
    "weekly": "week",
    "by week": "week",
    "each week": "week",
    "monthly": "month",
    "by month": "month",
    "each month": "month",
    "per month": "month",
    "quarterly": "quarter",
    "by quarter": "quarter",
    "each quarter": "quarter",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "by year": "year",
    "each year": "year",
    "per year": "year",
}

WORD_TO_NUMBER: Dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20, "fifty": 50, "hundred": 100,
}


def score_intent_keywords(query_lower: str) -> Dict[str, float]:
    """Return a keyword-match score per intent (used in keyword-fallback mode)."""
    scores: Dict[str, float] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if kw in query_lower:
                # Multi-word phrases worth twice as much
                score += 2.0 if " " in kw else 1.0
        scores[intent] = score
    return scores


def resolve_aggregation(query_lower: str) -> str:
    """Pick the aggregation type mentioned in the query, defaulting to 'sum'."""
    # Multi-word phrases first
    for phrase in sorted(AGGREGATION_MAP, key=len, reverse=True):
        if " " in phrase and phrase in query_lower:
            return AGGREGATION_MAP[phrase]
    for word, agg in AGGREGATION_MAP.items():
        if " " not in word and re.search(rf'\b{re.escape(word)}\b', query_lower):
            return agg
    return "sum"


def resolve_direction(query_lower: str) -> str:
    """Pick ranking direction ('top' / 'bottom') from the query."""
    for word, direction in DIRECTION_MAP.items():
        if re.search(rf'\b{re.escape(word)}\b', query_lower):
            return direction
    return "top"


def resolve_granularity(query_lower: str) -> str:
    """Pick time granularity from the query, defaulting to 'month'."""
    for phrase in sorted(GRANULARITY_MAP, key=len, reverse=True):
        if phrase in query_lower:
            return GRANULARITY_MAP[phrase]
    return "month"


def extract_k_value(query_lower: str) -> int:
    """Extract the K value for top-K queries (e.g. 'top 5' → 5)."""
    # Digit following a ranking word
    m = re.search(r'\b(?:top|bottom|best|worst|highest|lowest)\s+(\d+)\b', query_lower)
    if m:
        return int(m.group(1))
    # Written-out numbers
    for word, num in WORD_TO_NUMBER.items():
        if re.search(rf'\b{re.escape(word)}\b', query_lower):
            return num
    # Bare digit before "items / products / results"
    m = re.search(r'\b(\d+)\s+(?:items?|products?|categories|results?|customers?|employees?)\b', query_lower)
    if m:
        return int(m.group(1))
    return 10


def expand_with_synonyms(query_tokens: List[str]) -> List[str]:
    """
    Expand query tokens with business synonyms to improve column matching.
    Example: ['sales'] → ['sales', 'revenue'] so a 'Revenue' column is also scored.
    """
    expanded = list(query_tokens)
    for canonical, synonyms in BUSINESS_SYNONYMS.items():
        for syn in synonyms:
            if syn in query_tokens and canonical not in expanded:
                expanded.append(canonical)
        if canonical in query_tokens:
            for syn in synonyms:
                if syn not in expanded:
                    expanded.append(syn)
    return expanded
