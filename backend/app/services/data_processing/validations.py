"""
Financial integrity validations (CP-17). STRICTLY REPORT-ONLY — these never
mutate data, they only produce `quality` findings (warnings) with examples so
the user can investigate. A financial pipeline should surface these, not hide
them, but must not "fix" them by guessing.

Findings:
  1. Duplicate business keys with CONFLICTING amounts (same Invoice ID, two
     different totals) — a data-entry / integration red flag.
  2. Rows violating qty × unit_price ≈ amount (±1%) when all three columns are
     present (column ROLES matched generically by name — a hint only, never a
     cleaning gate, and only used for this non-destructive check).
  3. Dates in the future or before 1990 (likely typos / serial mishaps).
"""
import re
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from app.services.data_processing.type_detector import parse_numeric_series

MAX_EXAMPLES = 6

# Generic role hints — assist detection of the qty×price×amount relationship
# ONLY (a report-only check). They never decide any value-level cleaning.
_QTY_RE    = re.compile(r"(?i)\b(qty|quantity|units?|count)\b")
_PRICE_RE  = re.compile(r"(?i)\b(unit[\s_]?price|price|rate|cost)\b")
_AMOUNT_RE = re.compile(r"(?i)\b(amount|line[\s_]?total|total|value|subtotal)\b")
_KEY_RE    = re.compile(r"(?i)\b(invoice|order|ref(erence)?|txn|transaction|receipt|id|no|number)\b")


def _numeric(df: pd.DataFrame, col: str) -> pd.Series:
    s = df[col]
    if pd.api.types.is_numeric_dtype(s):
        return s
    parsed, _ = parse_numeric_series(s)
    return parsed


def run_validations(df: pd.DataFrame, type_map: Dict[str, str]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if df is None or len(df) == 0:
        return findings
    cols = list(df.columns)

    # ── 1. Duplicate business keys with conflicting amounts ───────────────────
    # Candidate key = mostly-unique column (identifier-ish) that still has some
    # repeats. For each repeated key, if a numeric column differs within the
    # group, that's a conflict.
    numeric_cols = [c for c in cols
                    if type_map.get(c) in ("numeric",) or pd.api.types.is_numeric_dtype(df[c])]
    for key in cols:
        ser = df[key].dropna()
        if len(ser) < 3:
            continue
        # A numeric AMOUNT column is not a business key — exclude it, otherwise a
        # repeated amount (20 twice) looks like a "conflicting key".
        if pd.api.types.is_numeric_dtype(df[key]) or type_map.get(key) == "numeric":
            continue
        uniq_ratio = ser.nunique() / len(ser)
        looks_key = _KEY_RE.search(str(key)) is not None
        # key-like: a key-ish NAME, or a very high-uniqueness identifier column,
        # with at least one repeat
        if not ((looks_key or uniq_ratio >= 0.9) and ser.duplicated().any()):
            continue
        dup_keys = ser[ser.duplicated(keep=False)]
        conflict_examples = []
        conflict_count = 0
        for kval, grp in df[df[key].isin(dup_keys.unique())].groupby(key):
            for ncol in numeric_cols:
                if ncol == key:
                    continue
                vals = _numeric(grp, ncol).dropna().round(4).unique()
                if len(vals) > 1:
                    conflict_count += 1
                    if len(conflict_examples) < MAX_EXAMPLES:
                        conflict_examples.append({
                            "row": None, "column": str(ncol),
                            "from": f'{key}={kval}',
                            "to": f'conflicting {ncol}: {", ".join(map(str, vals[:4]))}',
                        })
        if conflict_count:
            findings.append({
                "id": f"quality.conflicting_key.{key}",
                "category": "quality", "column": str(key),
                "title": f'"{key}" has {conflict_count} duplicate key(s) with conflicting values',
                "description": "The same identifier appears more than once with different amounts — "
                               "verify these rows (this is flagged, not changed).",
                "affected_count": conflict_count, "examples": conflict_examples,
                "enabled": False, "overridable": [],
            })
            break  # one key-conflict finding is enough signal

    # ── 2. qty × unit_price ≈ amount ─────────────────────────────────────────
    qty_c   = next((c for c in cols if _QTY_RE.search(str(c))), None)
    price_c = next((c for c in cols if _PRICE_RE.search(str(c))), None)
    amt_c   = next((c for c in cols if _AMOUNT_RE.search(str(c)) and c not in (qty_c, price_c)), None)
    if qty_c and price_c and amt_c:
        q = _numeric(df, qty_c); p = _numeric(df, price_c); a = _numeric(df, amt_c)
        expected = q * p
        both = expected.notna() & a.notna() & (a.abs() > 0)
        rel_err = (expected - a).abs() / a.abs().where(a.abs() > 0, np.nan)
        bad = both & (rel_err > 0.01)
        cnt = int(bad.sum())
        if cnt:
            examples = []
            for i in df.index[bad][:MAX_EXAMPLES]:
                examples.append({
                    "row": int(i) + 2, "column": str(amt_c),
                    "from": f'{qty_c}×{price_c}={expected.loc[i]:.2f}',
                    "to": f'{amt_c}={a.loc[i]:.2f} (mismatch)',
                })
            findings.append({
                "id": f"quality.qty_price_amount",
                "category": "quality", "column": str(amt_c),
                "title": f'{cnt} row(s) where {qty_c} × {price_c} ≠ {amt_c}',
                "description": f'"{amt_c}" does not equal {qty_c} × {price_c} (±1%) — possible '
                               f'pricing or entry errors (flagged, not changed).',
                "affected_count": cnt, "examples": examples,
                "enabled": False, "overridable": [],
            })

    # ── 3. Out-of-range dates (future / before 1990) ─────────────────────────
    today = pd.Timestamp.today().normalize()
    floor = pd.Timestamp("1990-01-01")
    for col in cols:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            dt = s
        elif type_map.get(col) == "datetime":
            dt = pd.to_datetime(s, errors="coerce", format="mixed")
        else:
            continue
        dt = dt.dropna()
        if len(dt) == 0:
            continue
        oob = (dt > today) | (dt < floor)
        cnt = int(oob.sum())
        if cnt:
            examples = []
            for i in dt.index[oob][:MAX_EXAMPLES]:
                examples.append({
                    "row": int(i) + 2, "column": str(col),
                    "from": dt.loc[i].strftime("%Y-%m-%d"),
                    "to": "out of range (future or pre-1990)",
                })
            findings.append({
                "id": f"quality.date_range.{col}",
                "category": "quality", "column": str(col),
                "title": f'{cnt} date(s) in "{col}" are in the future or before 1990',
                "description": "Likely typos or serial-date mishaps — verify (flagged, not changed).",
                "affected_count": cnt, "examples": examples,
                "enabled": False, "overridable": [],
            })

    return findings
