"""
Conversational single-cell editor assistant, via OpenRouter.

Reuses the same model list / HTTP call helper as llm_parser.py (the NLP query
parser) so there's only one place that knows how to talk to OpenRouter.
Lets the user ask about, or directly request, a new value for one specific
dataset cell from the Browse Full Data / Highlight Issues chat popover.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.services.nlp.llm_parser import request_completion, llm_available

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a helpful data-cleaning assistant embedded in a spreadsheet-style \
dataset editor. The user is looking at ONE specific cell and can ask you to explain what's \
wrong with it, suggest a fix, or tell you directly what value to put there.

Always reply with ONLY valid JSON, no markdown fences, in this exact shape:
{"reply": "<a short, natural, conversational answer to show the user>", "suggested_value": <string or null>}

Rules:
- "reply" is shown directly in a chat bubble — be concise, friendly, and specific to this cell.
- "suggested_value" is the exact new value you'd apply to this cell right now.
  - If the user explicitly gives a value ("set it to North", "make it 42", "change to Male"),
    put that value (their literal text) in suggested_value.
  - If the user asks for a suggestion ("what should this be?", "fix it", "what's wrong here?")
    and you can infer one confident, specific value (e.g. an obvious typo of a value that
    appears in the sample values, or an obvious formatting fix), propose ONE exact value in
    suggested_value AND explain your reasoning in "reply".
  - If you are just answering a question, explaining, or aren't confident enough to propose
    one exact value, set suggested_value to null.
- Never invent facts about the row's OTHER columns — you were not given them.
- Keep replies to 1-3 sentences."""


def _build_user_prompt(column: str, current_value: Optional[str],
                        sample_values: List[str], message: str) -> str:
    samples = ", ".join(f'"{v}"' for v in sample_values[:15]) or "(no other values available)"
    cur = "empty / missing" if current_value in (None, "") else f'"{current_value}"'
    return (
        f'Column: "{column}"\n'
        f'Current cell value: {cur}\n'
        f'Other sample values seen in this column: {samples}\n\n'
        f'User message: "{message}"\n\n'
        "Return the JSON response:"
    )


def _parse_response(raw: str) -> Optional[Dict[str, Any]]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    if not data or "reply" not in data:
        logger.warning("cell-chat: unparseable LLM response: %r", raw[:200])
        return None

    suggested = data.get("suggested_value")
    if suggested is not None:
        suggested = str(suggested)
    return {"reply": str(data["reply"]), "suggested_value": suggested}


def chat_about_cell(column: str, current_value: Optional[str], sample_values: List[str],
                     message: str, history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    Returns {"reply": str, "suggested_value": str|None}, or None if every
    model failed (caller should surface a "assistant unavailable" error).
    """
    if not llm_available():
        return None

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for h in (history or [])[-8:]:
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user",
                      "content": _build_user_prompt(column, current_value, sample_values, message)})

    payload_base = {"messages": messages, "temperature": 0.2, "max_tokens": 300}

    raw = request_completion(payload_base, is_usable=lambda r: _parse_response(r) is not None)
    if raw is None:
        logger.warning("cell-chat: all OpenRouter models/keys exhausted")
        return None
    return _parse_response(raw)


# ── Column-level chat (right-click a column header) ──────────────────────────

# Whitelisted server-side — anything else the model emits is dropped to null
# rather than trusted, since these names drive real bulk data transforms.
COLUMN_ACTION_TYPES = {
    "standardize_date", "standardize_number", "trim_whitespace",
    "change_case", "replace_value", "fill_missing", "set_all",
}

_COLUMN_SYSTEM_PROMPT = """You are a helpful data-cleaning assistant embedded in a spreadsheet-style \
dataset editor. The user is looking at an ENTIRE COLUMN (not a single cell) and wants to ask \
about it or apply a bulk transformation to every value in it.

Always reply with ONLY valid JSON, no markdown fences, in this exact shape:
{"reply": "<short conversational answer>", "action": null | {"type": "<action type>", "params": {...}}}

Available action types (use EXACTLY these strings, nothing else):
- "standardize_date": params {"format": "<Python strftime format, default \\"%Y-%m-%d\\">", "dayfirst": true|false}
  Use when the user wants dates in one consistent format (e.g. "make all dates the same", "use YYYY-MM-DD").
- "standardize_number": params {} — parses inconsistent number formats (commas, currency symbols, % signs) into plain numbers.
- "trim_whitespace": params {} — strips leading/trailing/extra spaces from every value.
- "change_case": params {"case": "upper"|"lower"|"title"}
- "replace_value": params {"from": "<exact current value>", "to": "<new value>"} — replaces one specific value everywhere it appears in the column.
- "fill_missing": params {"value": "<value to use for every blank/missing cell>"}
- "set_all": params {"value": "<value>"} — overwrites EVERY cell in the column with this one value. Only use when the user clearly wants to blank/reset the whole column, not for a normal fix.

Rules:
- Only set "action" when the user has given you enough to act on RIGHT NOW — otherwise ask a
  brief clarifying question in "reply" and leave action null.
- "reply" briefly states what you're about to do. The frontend always shows a preview (how many
  cells change, a few before/after examples) with its own Apply button before anything is saved
  — you do not need to ask the user to confirm yourself.
- Never invent a value you weren't given or couldn't infer from the sample values.
- Keep replies to 1-3 sentences."""


def _build_column_user_prompt(column: str, dtype_label: str, sample_values: List[str],
                               null_count: int, total_rows: int, message: str) -> str:
    samples = ", ".join(f'"{v}"' for v in sample_values[:15]) or "(no values)"
    return (
        f'Column: "{column}" (detected type: {dtype_label})\n'
        f'Total rows: {total_rows}, missing/blank: {null_count}\n'
        f'Sample values: {samples}\n\n'
        f'User message: "{message}"\n\n'
        "Return the JSON response:"
    )


def _parse_column_response(raw: str) -> Optional[Dict[str, Any]]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    if not data or "reply" not in data:
        logger.warning("column-chat: unparseable LLM response: %r", raw[:200])
        return None

    action = data.get("action")
    if isinstance(action, dict):
        if action.get("type") not in COLUMN_ACTION_TYPES:
            action = None
        else:
            action = {"type": action["type"], "params": action.get("params") or {}}
    else:
        action = None

    return {"reply": str(data["reply"]), "action": action}


def chat_about_column(column: str, dtype_label: str, sample_values: List[str], null_count: int,
                       total_rows: int, message: str,
                       history: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """
    Returns {"reply": str, "action": {"type": str, "params": dict}|None}, or
    None if every model failed (caller should surface an "unavailable" error).
    """
    if not llm_available():
        return None

    messages = [{"role": "system", "content": _COLUMN_SYSTEM_PROMPT}]
    for h in (history or [])[-8:]:
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": _build_column_user_prompt(
        column, dtype_label, sample_values, null_count, total_rows, message)})

    payload_base = {"messages": messages, "temperature": 0.1, "max_tokens": 300}

    raw = request_completion(payload_base, is_usable=lambda r: _parse_column_response(r) is not None)
    if raw is None:
        logger.warning("column-chat: all OpenRouter models/keys exhausted")
        return None
    return _parse_column_response(raw)
