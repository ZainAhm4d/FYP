"""
LLM-based query parser using OpenRouter.

Replaces the keyword/embedding NLP stack when OPENROUTER_API_KEY is set.
Falls back gracefully to the local keyword system on any failure.

The LLM receives the user's query + dataset column list and returns the same
parameter structure that the keyword/embedding pipeline produces, so the rest
of the pipeline (QueryExecutor, ChartFactory, ChartBuilder) is unchanged.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_DEFAULT_KEY_COOLDOWN = 60.0     # seconds, used when OpenRouter gives no retry_after
_DEAD_KEY_COOLDOWN = 3600.0      # 401/402/403 — likely won't self-resolve soon


class _KeyPool:
    """
    Round-robins across configured OpenRouter API keys and tracks which ones
    are temporarily "cooling down" so a request never has to wait on a key
    that's known to be unusable when another key is available right now.

    Cooldowns are tracked per (model, key) rather than per key alone: a 429
    on OpenRouter's free tier is frequently the *model's* upstream provider
    being congested, not the account being exhausted — the same key often
    works fine on a different model immediately. Only genuine key problems
    (401/402/403 — invalid, disabled, out of credits) cool the key down
    globally across all models, via the special model key `_DEAD_KEY_SCOPE`.
    """

    _DEAD_KEY_SCOPE = "__dead__"

    def __init__(self, keys: List[str]):
        self._keys = keys
        self._cooldowns: Dict[Tuple[str, str], float] = {}
        self._idx = 0
        self._lock = threading.Lock()

    def available_keys(self, model: str) -> List[str]:
        """Keys usable for this model right now (not cooling down for this
        model specifically, and not globally dead), ordered starting from a
        rotating offset so load spreads evenly instead of always hammering
        the first key until it dies."""
        now = time.time()
        with self._lock:
            offset = self._idx % len(self._keys)
            self._idx += 1
            ordered = self._keys[offset:] + self._keys[:offset]
        return [
            k for k in ordered
            if self._cooldowns.get((model, k), 0.0) <= now
            and self._cooldowns.get((self._DEAD_KEY_SCOPE, k), 0.0) <= now
        ]

    def mark_cooldown(self, key: str, seconds: float, model: Optional[str] = None) -> None:
        """model=None marks the key dead globally (all models); otherwise
        the cooldown only applies to that specific model."""
        scope = model or self._DEAD_KEY_SCOPE
        with self._lock:
            self._cooldowns[(scope, key)] = time.time() + max(seconds, 1.0)

    def __len__(self) -> int:
        return len(self._keys)


_key_pool: Optional[_KeyPool] = None
_key_pool_lock = threading.Lock()


def _get_api_keys() -> List[str]:
    """Merge OPENROUTER_API_KEY (always first, if set) with the optional
    OPENROUTER_API_KEYS list, de-duplicated, order preserved. Both settings
    accept a single key or a comma-separated list, so it works whether the
    extra keys were added to OPENROUTER_API_KEY itself or kept separate."""
    keys: List[str] = []
    for raw in (settings.OPENROUTER_API_KEY, settings.OPENROUTER_API_KEYS):
        for k in (raw or "").split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


def _get_key_pool() -> Optional[_KeyPool]:
    global _key_pool
    keys = _get_api_keys()
    if not keys:
        return None
    if _key_pool is None:
        with _key_pool_lock:
            if _key_pool is None:
                _key_pool = _KeyPool(keys)
    return _key_pool

# Intents the executor pipeline actually supports via the LLM mapping below.
# Anything else (including the model's explicit "unclear") triggers clarification.
_VALID_INTENTS = {
    "trend_over_time",
    "category_comparison",
    "distribution_analysis",
    "top_k_items",
    "scatter_relationship",
}

# Shown to the user when the model cannot map the question to a real analysis.
_LLM_CLARIFY = (
    "I couldn't tell what kind of analysis you're after. "
    "Try being more specific, for example:\n"
    "- 'show sales trend by month' - trend over time\n"
    "- 'compare revenue by category' - category comparison\n"
    "- 'top 5 products by revenue' - ranking\n"
    "- 'distribution of prices' - frequency breakdown\n"
    "- 'correlation between price and quantity' - scatter plot"
)

# Models tried in order — if the first is rate-limited or unavailable, next is tried.
# All confirmed free AND live on OpenRouter (spot-checked directly against
# /api/v1/models + a real completion call — OpenRouter's free-tier lineup
# rotates/deprecates fairly often, so re-verify this list if the LLM path
# starts silently falling back to keyword NLP more than expected).
# Different providers so rarely all congested together.
_FALLBACK_MODELS = [
    "google/gemma-4-31b-it:free",               # 31B instruction-tuned, excellent JSON output
    "google/gemma-4-26b-a4b-it:free",           # 26B MoE, fast and capable
    "nvidia/nemotron-3-nano-30b-a3b:free",      # 30B, strong instruction following
    "openai/gpt-oss-20b:free",                  # OpenAI OSS 20B, reliable JSON output
    "nvidia/nemotron-nano-9b-v2:free",          # 9B, small but usable as last resort
]

_SYSTEM_PROMPT = """You are a data query parser for a business intelligence dashboard.
Convert natural-language questions into a structured JSON query parameter object.

RULES:
- Return ONLY valid JSON. No explanation, no markdown, no code fences.
- Match column names EXACTLY as given in the column list (case-sensitive).
- intent must be exactly one of: trend_over_time, category_comparison, distribution_analysis, top_k_items, scatter_relationship, unclear
- Use intent "unclear" when the question is gibberish, is unrelated to analysing
  this dataset, or does not clearly map to any of the analyses above. Do NOT
  invent or guess an intent for nonsense or out-of-scope input.
- If the user asks for two or more DIFFERENT analyses in one sentence
  (e.g. "trend of revenue and also top products"), return intent "unclear" and
  set "clarification" to a short message listing the separate questions you saw.
- chart_type: if the user names a chart style (pie, donut, line, bar, column,
  stacked bar, horizontal bar, area, scatter), set chart_type accordingly
  (one of: auto, line, bar, horizontal_bar, stacked_bar, stacked_horizontal,
  area, pie, scatter); otherwise "auto". A named chart style must NOT change
  the intent — "pie chart of revenue by region" is category_comparison with
  chart_type "pie".
- filters: list of {column, value} for WHERE-style row filtering (e.g. "in north region" → [{"column":"Region","value":"North"}])
- secondary_dimensions: list of additional columns to group by alongside the primary dimension.
  Use when the user says "also show X", "mention X", "grouped by X and Y", "breakdown by X per Y".
  Example: "top customer and also mention product" → dimension_column:"Customer_Name", secondary_dimensions:["Product_Name"]
- k: number of results. Default 10. Use 1 ONLY if the user explicitly says "the top one", "single", "only one".
  "top customer" or "best product" without a number → k=10.
- aggregation: "sum" (default), "mean", "count", "min", "max"
- direction: "top" (default) or "bottom"

JSON schema:
{
  "intent": "<intent>",
  "chart_type": "auto",
  "clarification": null,
  "metric_column": "<numeric metric column>",
  "dimension_column": "<primary category/dimension column>",
  "secondary_dimensions": ["<optional extra columns to include in grouping>"],
  "time_column": "<date column — trend_over_time only>",
  "x_column": "<scatter X axis>",
  "y_column": "<scatter Y axis>",
  "column": "<distribution_analysis only>",
  "aggregation": "sum",
  "time_granularity": "month",
  "k": 10,
  "direction": "top",
  "sort_order": "desc",
  "filters": []
}"""


def _build_user_prompt(query_text: str, columns: List[Dict[str, Any]]) -> str:
    col_lines = "\n".join(
        f"  - {c['name']} ({c['category']})"
        for c in columns
    )
    return (
        f"Dataset columns:\n{col_lines}\n\n"
        f"User query: \"{query_text}\"\n\n"
        "Return the JSON parameter object:"
    )


def _parse_llm_response(raw: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from the model's response, tolerating minor formatting."""
    raw = raw.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find first {...} block
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    logger.warning("LLM returned unparseable response: %r", raw[:200])
    return None


def _llm_to_pipeline_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert the LLM JSON into the same structure parse_natural_query returns
    so the /natural endpoint needs zero changes.
    """
    intent = (data.get("intent") or "").strip()

    # Confidence/clarification gate: if the model couldn't map the question to a
    # real analysis (explicit "unclear", or any unexpected/empty intent), ask the
    # user to rephrase instead of hallucinating a chart. CH-04: the model's own
    # clarification (e.g. "that's two questions") is preferred when it wrote one.
    if intent not in _VALID_INTENTS:
        model_clarify = (data.get("clarification") or "").strip()
        return {
            "intent":        intent or "unclear",
            "confidence":    0.0,
            "parameters":    {},
            "clarification": model_clarify or _LLM_CLARIFY,
            "ready":         False,
            "nlp_mode":      "llm",
        }

    # CH-04: explicit chart-style request, validated and carried on every intent
    _ALLOWED_CHART_TYPES = {"line", "bar", "horizontal_bar", "stacked_bar",
                            "stacked_horizontal", "area", "pie", "scatter"}
    requested_chart = (data.get("chart_type") or "auto").strip().lower()
    if requested_chart not in _ALLOWED_CHART_TYPES:
        requested_chart = None

    # Build parameters dict — only include keys relevant to this intent
    params: Dict[str, Any] = {}

    sec = [s for s in (data.get("secondary_dimensions") or []) if s]

    if intent == "trend_over_time":
        if data.get("metric_column"):
            params["metric_column"] = data["metric_column"]
        if data.get("time_column"):
            params["time_column"] = data["time_column"]
        params["aggregation"]      = data.get("aggregation", "sum")
        params["time_granularity"] = data.get("time_granularity", "month")

    elif intent == "category_comparison":
        if data.get("metric_column"):
            params["metric_column"] = data["metric_column"]
        if data.get("dimension_column"):
            params["category_column"] = data["dimension_column"]
        if sec:
            params["secondary_dimensions"] = sec
        params["aggregation"] = data.get("aggregation", "sum")
        params["sort_order"]  = data.get("sort_order", "desc")

    elif intent == "distribution_analysis":
        if data.get("column"):
            params["column"] = data["column"]
        params["chart_preference"] = "auto"
        params["bins"]             = 10

    elif intent == "top_k_items":
        if data.get("metric_column"):
            params["metric_column"] = data["metric_column"]
        if data.get("dimension_column"):
            params["dimension_column"] = data["dimension_column"]
        if sec:
            params["secondary_dimensions"] = sec
        params["k"]           = int(data.get("k", 10))
        params["direction"]   = data.get("direction", "top")
        params["aggregation"] = data.get("aggregation", "sum")

    elif intent == "scatter_relationship":
        if data.get("x_column"):
            params["x_column"] = data["x_column"]
        if data.get("y_column"):
            params["y_column"] = data["y_column"]

    # Filters work across all intents
    filters = data.get("filters") or []
    if filters:
        params["filters"] = filters

    if requested_chart:
        params["requested_chart_type"] = requested_chart

    missing = _check_missing(intent, params)
    clarification = ("Could you clarify: " + "; and ".join(missing) + "?") if missing else None

    return {
        "intent":        intent,
        "confidence":    1.0,
        "parameters":    params,
        "clarification": clarification,
        "ready":         clarification is None and bool(params),
        "nlp_mode":      "llm",
    }


def _check_missing(intent: str, params: Dict[str, Any]) -> List[str]:
    missing = []
    if intent == "trend_over_time":
        if "metric_column" not in params:
            missing.append("which metric to track")
        if "time_column" not in params:
            missing.append("which date column to use")
    elif intent == "category_comparison":
        if "metric_column" not in params:
            missing.append("which metric to compare")
        if "category_column" not in params:
            missing.append("which category to group by")
    elif intent == "distribution_analysis":
        if "column" not in params:
            missing.append("which column to analyse")
    elif intent == "top_k_items":
        if "metric_column" not in params:
            missing.append("which metric to rank by")
        if "dimension_column" not in params:
            missing.append("which items to rank")
    elif intent == "scatter_relationship":
        if "x_column" not in params:
            missing.append("first numeric column (X axis)")
        if "y_column" not in params:
            missing.append("second numeric column (Y axis)")
    return missing


def _call_model(
    model: str,
    payload_base: Dict[str, Any],
    api_key: str,
) -> Tuple[Optional[str], Optional[str], float]:
    """
    Try one (model, key) combination once.

    Returns (content, cooldown_scope, retry_after_seconds):
      - content is the raw text response on success, else None.
      - cooldown_scope is None on success or a hard (non-key) failure;
        "model" when only this model is congested for this key (429 — the
        same key likely still works on a different model, so don't block it
        pool-wide); "dead" when the key itself is bad (401/402/403 — cool it
        down for every model).
      - retry_after_seconds is how long to cool down for (meaningful only
        when cooldown_scope is set).
    """
    payload = {**payload_base, "model": model}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost",
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(OPENROUTER_URL, json=payload, headers=headers)
    except Exception as exc:
        logger.error("Model %s call failed — %s", model, exc)
        return None, None, 0.0

    if resp.status_code == 429:
        try:
            retry_after = (
                resp.json()
                .get("error", {})
                .get("metadata", {})
                .get("retry_after_seconds", _DEFAULT_KEY_COOLDOWN)
            )
        except Exception:
            retry_after = _DEFAULT_KEY_COOLDOWN
        logger.warning(
            "Model %s rate-limited on this key — trying another key/model (cooldown %.0fs)",
            model, retry_after,
        )
        return None, "model", float(retry_after)

    if resp.status_code in (401, 402, 403):
        # Invalid, disabled, or out of credits — not model-specific, and
        # won't fix itself within this request, so cool it down for longer
        # across every model.
        logger.warning(
            "Model %s HTTP %s on this key — key looks dead, cooling down %.0fs across all models",
            model, resp.status_code, _DEAD_KEY_COOLDOWN,
        )
        return None, "dead", _DEAD_KEY_COOLDOWN

    if resp.status_code != 200:
        logger.error("Model %s HTTP %s — %s", model, resp.status_code, resp.text[:200])
        return None, None, 0.0

    try:
        return resp.json()["choices"][0]["message"]["content"], None, 0.0
    except (ValueError, KeyError, IndexError, TypeError):
        # OpenRouter occasionally returns 200 with a malformed/empty body
        # (e.g. an upstream provider error wrapped as a 200). Not a key
        # problem — try the next model.
        logger.error("Model %s returned 200 with unexpected body — %s", model, resp.text[:200])
        return None, None, 0.0


def request_completion(
    payload_base: Dict[str, Any],
    is_usable: Optional[callable] = None,
) -> Optional[str]:
    """
    Shared OpenRouter call path used by every LLM feature in this app (query
    parsing, cell chat, column chat). Tries the configured model first, then
    falls through _FALLBACK_MODELS; for each model, tries every configured
    API key (round-robin, skipping keys on cooldown) before moving to the
    next model — so a rate-limited or dead account fails over immediately
    instead of making the user wait. With only one key configured, behavior
    matches the original single-key retry-once-then-move-on logic.

    is_usable, if given, is called on each successful raw response text; a
    False return (e.g. unparseable JSON) is treated like a failed call and
    the next model/key is tried instead of returning garbage to the caller.

    Returns the raw model response text, or None if every (model, key)
    combination failed (caller should fall back to its own non-LLM path).
    """
    pool = _get_key_pool()
    if pool is None:
        return None

    primary = settings.OPENROUTER_MODEL
    model_queue = [primary] + [m for m in _FALLBACK_MODELS if m != primary]

    MAX_RETRY_WAIT = 12  # seconds — only used in the single-key case

    for model in model_queue:
        avail_keys = pool.available_keys(model)
        for api_key in avail_keys:
            content, cooldown_scope, retry_after = _call_model(model, payload_base, api_key)

            if cooldown_scope:
                pool.mark_cooldown(api_key, retry_after, model=None if cooldown_scope == "dead" else model)
                # Only worth a short blocking wait when there's no other key to
                # fall back to — with multiple keys, rotating is always faster
                # than waiting, which is the whole point of having them.
                if len(pool) == 1 and retry_after <= MAX_RETRY_WAIT:
                    logger.warning("Model %s rate-limited — retrying in %.1fs", model, retry_after)
                    time.sleep(retry_after)
                    content, cooldown_scope, retry_after = _call_model(model, payload_base, api_key)
                    if cooldown_scope:
                        pool.mark_cooldown(api_key, retry_after, model=None if cooldown_scope == "dead" else model)

            if content is None:
                continue  # try next key (or next model if keys exhausted)

            if is_usable is not None and not is_usable(content):
                logger.warning("Model %s returned unusable response — trying next", model)
                break  # not a key problem — move to the next model, not next key

            logger.info("LLM success via %s | response: %s", model, content[:200])
            return content

    logger.warning("All OpenRouter models/keys exhausted")
    return None


def parse_with_llm(
    query_text: str,
    columns: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Call OpenRouter and return a parse_natural_query-compatible dict.
    Returns None when every model/key combination fails, or the response
    can't be parsed, so the caller can use keyword NLP.
    """
    if _get_key_pool() is None:
        return None

    payload_base = {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_prompt(query_text, columns)},
        ],
        "temperature": 0,
        "max_tokens":  300,
    }

    content = request_completion(payload_base)
    if content is None:
        logger.warning("Falling back to keyword NLP")
        return None

    data = _parse_llm_response(content)
    if data is None:
        logger.warning("LLM returned unparseable JSON — falling back to keyword NLP")
        return None

    return _llm_to_pipeline_format(data)


def llm_available() -> bool:
    """True when at least one API key is configured."""
    return bool(_get_api_keys())
