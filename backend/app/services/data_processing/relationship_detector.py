"""
Relationship detector (CH-09) — suggests join keys between a user's datasets.

Evidence model (in order of weight):
1. Value overlap — containment of sampled distinct values. This is the ONLY
   gate: a pair with weak overlap is never suggested, no matter how similar
   the column names are ("id" columns everywhere must not create links).
2. Key-ness — uniqueness of each side, which also yields the cardinality
   (one_to_one / one_to_many / many_to_one / many_to_many).
3. Name similarity — assist-only signal folded into the confidence score.

All thresholds live in data_processing/config.py (CP-19 pattern).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List

import pandas as pd

from app.services.data_processing import config as C


def _snake(name: str) -> str:
    """customer_id / CustomerID / customer-id → 'customer id'."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    s = re.sub(r"[_\-.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _snake(a), _snake(b)).ratio()


_ID_NAME_RE = re.compile(
    r"\b(id|key|code|no|num|number|ref|reference|pk|fk|sku|uuid|guid)\b", re.IGNORECASE
)


def _looks_like_id_name(name: str) -> bool:
    """Whole-word match so 'amount' doesn't trip on 'no', etc."""
    return bool(_ID_NAME_RE.search(_snake(name)))


def _core_name(name: str) -> str:
    """Name with id/key/code/etc. tokens stripped — the 'business meaning'
    part, e.g. 'region_id' -> 'region', 'sale_id' -> 'sale'."""
    stripped = _ID_NAME_RE.sub(" ", _snake(name))
    return re.sub(r"\s+", " ", stripped).strip()


def _normalized_distincts(series: pd.Series) -> set:
    """Sampled distinct values, normalized for cross-file comparison."""
    vals = series.dropna()
    if vals.empty:
        return set()
    vals = vals.drop_duplicates()
    if len(vals) > C.REL_SAMPLE_DISTINCTS:
        vals = vals.sample(C.REL_SAMPLE_DISTINCTS, random_state=0)
    out = set()
    for v in vals:
        s = str(v).strip().casefold()
        # "1042.0" (numeric dtype) and "1042" (text) are the same key value
        if s.endswith(".0"):
            s = s[:-2]
        if s:
            out.add(s)
    return out


def _column_profile(df: pd.DataFrame, col: str) -> Dict[str, Any] | None:
    series = df[col]
    n = len(series)
    if n == 0:
        return None
    null_frac = float(series.isna().sum()) / n
    if null_frac > C.REL_MAX_NULL_FRACTION:
        return None
    non_null = series.dropna()
    distinct = int(non_null.nunique())
    if distinct <= 1:
        return None   # constant column can never be a key
    return {
        "name": col,
        "values": _normalized_distincts(series),
        "distinct": distinct,
        "unique_ratio": distinct / len(non_null) if len(non_null) else 0.0,
        "numeric": pd.api.types.is_numeric_dtype(series),
        "id_like_name": _looks_like_id_name(col),
    }


def _cardinality(left_unique: bool, right_unique: bool) -> str:
    if left_unique and right_unique:
        return "one_to_one"
    if left_unique:
        return "one_to_many"
    if right_unique:
        return "many_to_one"
    return "many_to_many"


def suggest_relationships(
    dfs: Dict[int, pd.DataFrame],
    names: Dict[int, str],
) -> List[Dict[str, Any]]:
    """
    Score every column pair across every dataset pair; return candidates that
    pass the containment gate, sorted by confidence (desc). Never mutates data.
    """
    profiles: Dict[int, List[Dict[str, Any]]] = {}
    for ds_id, df in dfs.items():
        cols = []
        for col in df.columns:
            p = _column_profile(df, col)
            if p and p["values"]:
                cols.append(p)
        profiles[ds_id] = cols

    ids = sorted(profiles.keys())
    candidates: List[Dict[str, Any]] = []

    for i, left_id in enumerate(ids):
        for right_id in ids[i + 1:]:
            for lp in profiles[left_id]:
                for rp in profiles[right_id]:
                    # dtype compatibility: numeric keys only join numeric-like
                    # (string-normalized digits still land in both sets).
                    # Two guards, both required:
                    #  (a) at least one side must be genuinely unique
                    #      (unique_ratio >= threshold) — two repeating
                    #      numeric measures (quantities, amounts) must never
                    #      match on their own.
                    #  (b) EVERY numeric side involved must independently be
                    #      a plausible key/FK candidate: its name looks
                    #      id-like (id/key/code/no/ref/pk/fk), or it has
                    #      enough distinct values that a high unique_ratio
                    #      isn't just a small-sample fluke. Without this, a
                    #      5-row "qty_on_hand" column (values 1-5) is
                    #      "100% unique" purely from having few rows, and
                    #      coincidentally overlaps with any real ID column
                    #      covering that same small range — (a) alone lets
                    #      that pass just because the OTHER side (e.g. a
                    #      real "customer_id") is unique.
                    if lp["numeric"] and rp["numeric"]:
                        def _numeric_eligible(p):
                            return p["id_like_name"] or p["distinct"] >= C.REL_MIN_NUMERIC_KEY_DISTINCT
                        one_side_unique = (lp["unique_ratio"] >= C.REL_UNIQUE_RATIO
                                            or rp["unique_ratio"] >= C.REL_UNIQUE_RATIO)
                        if not (one_side_unique and _numeric_eligible(lp) and _numeric_eligible(rp)):
                            continue

                        # Small sequential-integer domains (region_id: 1-5)
                        # are near-guaranteed to value-overlap with ANY other
                        # auto-increment ID column with more rows (sale_id:
                        # 1-30) by pure coincidence — containment evidence
                        # alone isn't trustworthy there. Require the names to
                        # share some resemblance once id/key/code tokens are
                        # stripped, unless the raw names are identical.
                        if (min(lp["distinct"], rp["distinct"]) < C.REL_SMALL_DISTINCTS
                                and _snake(lp["name"]) != _snake(rp["name"])):
                            core_sim = _name_similarity(
                                _core_name(lp["name"]) or _snake(lp["name"]),
                                _core_name(rp["name"]) or _snake(rp["name"]),
                            )
                            if core_sim < C.REL_MIN_CORE_NAME_SIM_SMALL_DOMAIN:
                                continue
                    overlap = lp["values"] & rp["values"]
                    matched = len(overlap)
                    if matched == 0:
                        continue
                    smaller = min(len(lp["values"]), len(rp["values"]))
                    containment = matched / smaller if smaller else 0.0
                    if containment < C.REL_MIN_CONTAINMENT:
                        continue
                    min_matches = (
                        C.REL_MIN_MATCHES
                        if smaller >= C.REL_SMALL_DISTINCTS
                        else max(2, int(smaller * C.REL_SMALL_MIN_FRACTION))
                    )
                    if matched < min_matches:
                        continue

                    left_unique = lp["unique_ratio"] >= C.REL_UNIQUE_RATIO
                    right_unique = rp["unique_ratio"] >= C.REL_UNIQUE_RATIO
                    keyness = max(lp["unique_ratio"], rp["unique_ratio"])
                    name_sim = _name_similarity(lp["name"], rp["name"])
                    confidence = (
                        C.REL_CONTAINMENT_WEIGHT * containment
                        + C.REL_KEYNESS_WEIGHT * keyness
                        + C.REL_NAME_WEIGHT * name_sim
                    )
                    candidates.append({
                        "left_dataset_id": left_id,
                        "left_dataset_name": names.get(left_id, str(left_id)),
                        "left_column": lp["name"],
                        "right_dataset_id": right_id,
                        "right_dataset_name": names.get(right_id, str(right_id)),
                        "right_column": rp["name"],
                        "cardinality": _cardinality(left_unique, right_unique),
                        "confidence": round(confidence, 3),
                        "containment": round(containment, 3),
                        "matched_distinct": matched,
                        "matched_examples": sorted(overlap)[:5],
                    })

    # Best pair per dataset pair first; drop weaker duplicates of the same
    # column pair reached via different sampling
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    return candidates


def estimate_join_rows(ldf: pd.DataFrame, lkey: str,
                       rdf: pd.DataFrame, rkey: str) -> int:
    """Projected inner-join row count via key group sizes (no actual merge)."""
    lcounts = ldf[lkey].astype(str).str.strip().value_counts()
    rcounts = rdf[rkey].astype(str).str.strip().value_counts()
    common = lcounts.index.intersection(rcounts.index)
    if len(common) == 0:
        return 0
    return int((lcounts.loc[common] * rcounts.loc[common]).sum())
