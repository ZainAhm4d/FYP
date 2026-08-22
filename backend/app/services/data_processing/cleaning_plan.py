"""
Interactive cleaning: build a PLAN of proposed changes (dry-run, cell-level
examples, nothing modified), let the user approve/adjust, then APPLY only the
selected operations.

Plan structure:
{
  "operations": [
    {
      "id": "normalize.Region",
      "category": "normalization" | "sanitation" | "missing" | "duplicates" | "conversion",
      "column": "Region" | None,
      "title": "...",
      "description": "...",
      "affected_count": 4,
      "examples": [{"row": 5, "column": "Region", "from": "norht", "to": "North"}, ...],
      "enabled": true,          # default recommendation
      "overridable": ["disable", "fill_zero", "fill_value"],   # what chat can do
    }, ...
  ],
  "summary": {...}
}
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.data_processing.cleaner import DataCleaner
from app.services.data_processing.type_detector import (
    TypeDetector, parse_numeric_series, parse_numeric_value,
)

MAX_EXAMPLES = 8

# Op categories that change VALUES (vs. structural sanitation). A brand-new op
# in one of these categories on refreshed data must go back to the user for
# review rather than being auto-applied (CP-05).
_VALUE_CATEGORIES = {"missing", "normalization", "conversion", "duplicates"}


def _op_kind(op_id: str, column: Optional[str]) -> str:
    """
    Stable operation identity independent of a column's data. "convert.numeric.Revenue"
    → "convert.numeric"; "sanitation.whitespace" → "sanitation.whitespace".
    Column names may contain dots, so strip the exact ".<column>" suffix.
    """
    if column is not None and op_id.endswith("." + str(column)):
        return op_id[: -(len(str(column)) + 1)]
    return op_id


def _examples_from_mask(df: pd.DataFrame, col: str, mask, new_values=None) -> List[Dict]:
    """First N changed cells as {row, column, from, to} dicts."""
    out = []
    idx = df.index[mask][:MAX_EXAMPLES]
    for i in idx:
        frm = df.at[i, col]
        to = new_values.at[i] if new_values is not None else None
        out.append({
            "row": int(i) + 2,   # +2 = 1-based + header row, matches what users see in Excel
            "column": col,
            "from": None if pd.isna(frm) else str(frm),
            "to": None if (to is None or (isinstance(to, float) and np.isnan(to))) else str(to),
        })
    return out


def build_plan(df: pd.DataFrame) -> Dict[str, Any]:
    """Dry-run the full pipeline and record every proposed change."""
    operations: List[Dict] = []
    work = df.copy()

    def _is_text(s):
        return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)

    # ── 1. Sanitation proposals ───────────────────────────────────────────────
    # Whitespace
    ws_examples, ws_count = [], 0
    for col in work.columns:
        if not _is_text(work[col]):
            continue
        cleaned = (work[col].astype(str)
                   .str.replace('\xa0', ' ', regex=False)
                   .str.replace('​', '', regex=False)
                   .str.replace(r'\s{2,}', ' ', regex=True)
                   .str.strip())
        cleaned = cleaned.where(work[col].notna(), work[col])
        changed = (cleaned != work[col].astype(str)) & work[col].notna()
        if changed.any():
            ws_count += int(changed.sum())
            if len(ws_examples) < MAX_EXAMPLES:
                ws_examples += _examples_from_mask(work, col, changed, cleaned)
    if ws_count:
        operations.append({
            "id": "sanitation.whitespace", "category": "sanitation", "column": None,
            "title": "Fix stray whitespace",
            "description": "Remove extra/invisible spaces (double spaces, non-breaking spaces) from text cells",
            "affected_count": ws_count, "examples": ws_examples[:MAX_EXAMPLES],
            "enabled": True, "overridable": ["disable"],
        })

    # Apply whitespace to the working copy so later stages see clean text
    work, _ = DataCleaner.sanitize_dataframe(work)
    # sanitize also did sentinels/headers/rows/junk — rebuild those proposals
    # from the ORIGINAL so each is independently listed:
    orig = df

    # Sentinels
    sen_examples, sen_count, sen_cols = [], 0, set()
    for col in orig.columns:
        if not _is_text(orig[col]):
            continue
        mask = orig[col].astype(str).str.strip().str.lower().isin(DataCleaner.MISSING_SENTINELS)
        mask &= orig[col].notna()
        if mask.any():
            sen_count += int(mask.sum())
            sen_cols.add(col)
            if len(sen_examples) < MAX_EXAMPLES:
                sen_examples += _examples_from_mask(orig, col, mask)
    if sen_count:
        for e in sen_examples:
            e["to"] = "(blank / missing)"
        operations.append({
            "id": "sanitation.sentinels", "category": "sanitation", "column": None,
            "title": 'Convert placeholders ("N/A", "-", Excel errors) to blank',
            "description": f'Placeholder values in {len(sen_cols)} column(s) will be treated as missing data',
            "affected_count": sen_count, "examples": sen_examples[:MAX_EXAMPLES],
            "enabled": True, "overridable": ["disable"],
        })

    # Repeated header rows
    header_mask = DataCleaner.detect_header_rows(orig)
    if header_mask.any():
        operations.append({
            "id": "sanitation.headers", "category": "sanitation", "column": None,
            "title": "Remove repeated header rows",
            "description": "Rows that duplicate the column headers (from stitched exports)",
            "affected_count": int(header_mask.sum()),
            "examples": [{"row": int(i) + 2, "column": "(whole row)", "from": "header text", "to": "(row removed)"}
                         for i in orig.index[header_mask][:MAX_EXAMPLES]],
            "enabled": True, "overridable": ["disable"],
        })

    # Empty rows
    empty_rows = orig.isna().all(axis=1)
    if empty_rows.any():
        operations.append({
            "id": "sanitation.empty_rows", "category": "sanitation", "column": None,
            "title": "Remove completely empty rows",
            "description": "Rows with no data in any column",
            "affected_count": int(empty_rows.sum()),
            "examples": [{"row": int(i) + 2, "column": "(whole row)", "from": "(empty)", "to": "(row removed)"}
                         for i in orig.index[empty_rows][:MAX_EXAMPLES]],
            "enabled": True, "overridable": ["disable"],
        })

    # Junk columns — evaluated AFTER header/empty-row removal (a repeated
    # header row would otherwise give a junk column one non-null value and
    # hide it from the plan)
    post_rows = orig[~header_mask].dropna(how='all')
    for col in post_rows.columns:
        missing_pct = post_rows[col].isna().mean() if len(post_rows) else 1.0
        if missing_pct == 1.0 or (str(col).startswith('Unnamed:') and missing_pct >= 0.95):
            operations.append({
                "id": f"sanitation.drop_column.{col}", "category": "sanitation", "column": str(col),
                "title": f'Drop empty column "{col}"',
                "description": f'{missing_pct:.0%} empty — carries no information',
                "affected_count": 1, "examples": [],
                "enabled": True, "overridable": ["disable"],
            })

    # ── 1b. Total / Subtotal / footer rows (CP-12) ────────────────────────────
    agg_mask = DataCleaner.detect_aggregate_rows(work)
    if agg_mask.any():
        operations.append({
            "id": "sanitation.aggregate_rows", "category": "sanitation", "column": None,
            "title": f"Remove {int(agg_mask.sum())} total/subtotal row(s)",
            "description": "Summary rows (Total, Subtotal, Grand Total) double-count in every "
                           "sum and average — removing them keeps aggregates correct.",
            "affected_count": int(agg_mask.sum()),
            "examples": [{"row": int(i) + 2, "column": "(whole row)",
                          "from": " · ".join(str(v) for v in work.loc[i].tolist()[:4]),
                          "to": "(summary row removed)"}
                         for i in work.index[agg_mask][:MAX_EXAMPLES]],
            "enabled": True, "overridable": ["disable"],
        })

    # ── 2. Type detection on sanitized copy ───────────────────────────────────
    type_map, format_info = TypeDetector.detect_all_types_ex(work)

    # Simulate the canonical pipeline so the plan's numbers match what apply
    # will actually do: normalize labels → (dedupe count) → convert types.
    # Missing counts are then taken POST-conversion so parse failures ("abc" in
    # a currency column) are counted, shown, and offered for handling (CP-02).
    work_norm, _preview_norm = DataCleaner.normalize_categorical_columns(work.copy(), type_map)

    # Per-column conversion simulation
    convert_sim: Dict[str, Dict] = {}
    for col, ctype in type_map.items():
        if col not in work_norm.columns:
            continue
        if ctype == 'numeric' and not pd.api.types.is_numeric_dtype(work_norm[col]):
            parsed, info = parse_numeric_series(work_norm[col])
            fail_mask = work_norm[col].notna() & parsed.isna()
            convert_sim[col] = {"kind": "numeric", "parsed": parsed,
                                "fail_mask": fail_mask, "info": info}
        elif ctype == 'datetime' and not pd.api.types.is_datetime64_any_dtype(work_norm[col]):
            state = TypeDetector.sniff_dayfirst_state(work_norm[col])
            dayfirst = state == "dayfirst"
            parsed = pd.to_datetime(work_norm[col], errors='coerce', dayfirst=dayfirst, format='mixed')
            fail_mask = work_norm[col].notna() & parsed.isna()
            convert_sim[col] = {"kind": "datetime", "parsed": parsed,
                                "fail_mask": fail_mask, "dayfirst": dayfirst,
                                "dayfirst_state": state}

    # Fully-converted preview for post-conversion null counts
    work_conv = work_norm.copy()
    for col, sim in convert_sim.items():
        work_conv[col] = sim["parsed"]

    # Conversion proposals
    for col, sim in convert_sim.items():
        if sim["kind"] == "numeric":
            info = sim["info"]
            changed = work_norm[col].notna()
            fmt_bits = []
            if info.get('is_currency'): fmt_bits.append('currency values')
            if info.get('european_format'): fmt_bits.append('European decimal format (1.234,56)')
            if info.get('is_percent'): fmt_bits.append('percentages ("percent sign removed, 12.5% → 12.5")')
            if info.get('accounting_negatives'): fmt_bits.append('accounting negatives "(500)"')
            desc = ('Detected: ' + ', '.join(fmt_bits)) if fmt_bits \
                   else 'Numbers stored as text will become real numbers'
            op = {
                "id": f"convert.numeric.{col}", "category": "conversion", "column": str(col),
                "title": f'Read "{col}" as numbers',
                "description": desc,
                "affected_count": int(changed.sum()),
                "examples": _examples_from_mask(work_norm, col, changed, sim["parsed"].astype(str)),
                "enabled": True, "overridable": ["disable", "keep_text"],
            }
            # CP-01: ambiguous "1,234" columns need a user separator decision
            if info.get('separator_ambiguous'):
                ex = info.get('ambiguous_examples') or []
                ex_val = ex[0] if ex else "1,234"
                digits = ex_val.replace(',', '')
                op["choices"] = {
                    "kind": "separator",
                    "options": [
                        {"id": "us", "label": f'{ex_val} → {digits} (thousands separator)', "default": True},
                        {"id": "eu", "label": f'{ex_val} → {ex_val.replace(",", ".")} (decimal separator)'},
                    ],
                }
                op["description"] += (f' · The comma in values like "{ex_val}" is ambiguous — '
                                      f'assumed a thousands separator. Change below if it is a decimal.')
                op["overridable"] = ["disable", "keep_text", "separator"]
            operations.append(op)
        else:  # datetime
            dayfirst = sim["dayfirst"]
            parsed = sim["parsed"]
            state = sim.get("dayfirst_state", "monthfirst")
            changed = work_norm[col].notna() & parsed.notna()
            dt_op = {
                "id": f"convert.datetime.{col}", "category": "conversion", "column": str(col),
                "title": f'Read "{col}" as dates ({"day/month" if dayfirst else "month/day or ISO"})',
                "description": "Text dates become real dates so time charts work",
                "affected_count": int(changed.sum()),
                "examples": _examples_from_mask(work_norm, col, changed, parsed.dt.strftime('%Y-%m-%d')),
                "enabled": True, "overridable": ["disable", "keep_text"],
            }
            # CP-10: ambiguous day/month (every component ≤ 12) needs a choice
            if state == "ambiguous":
                ex_val = None
                for v in work_norm[col].dropna().astype(str):
                    if re.match(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}", v.strip()):
                        ex_val = v.strip()
                        break
                if ex_val:
                    d_dayfirst = pd.to_datetime(ex_val, dayfirst=True, errors='coerce')
                    d_monthfirst = pd.to_datetime(ex_val, dayfirst=False, errors='coerce')
                    lab_day = d_dayfirst.strftime('%Y-%m-%d') if pd.notna(d_dayfirst) else 'day/month'
                    lab_mon = d_monthfirst.strftime('%Y-%m-%d') if pd.notna(d_monthfirst) else 'month/day'
                    dt_op["choices"] = {
                        "kind": "dayfirst",
                        "options": [
                            {"id": "month", "label": f'{ex_val} → {lab_mon} (month/day)', "default": True},
                            {"id": "day", "label": f'{ex_val} → {lab_day} (day/month)'},
                        ],
                    }
                    dt_op["description"] += (f' · Dates like "{ex_val}" are ambiguous — assumed '
                                             f'month/day. Change below if your dates are day/month.')
                    dt_op["overridable"] = ["disable", "keep_text", "dayfirst"]
            operations.append(dt_op)

    # ── 2b. Currency / percent quality warnings (CP-13, CP-16) ────────────────
    for col, sim in convert_sim.items():
        if sim["kind"] != "numeric":
            continue
        info = sim["info"]
        # CP-13: mixed currencies in one column
        if info.get("mixed_currency"):
            curmap = info.get("currencies", {})
            top = sorted(curmap.items(), key=lambda kv: -kv[1])[:4]
            summary = ", ".join(f'{t} ×{c}' for t, c in top)
            operations.append({
                "id": f"quality.mixed_currency.{col}", "category": "quality", "column": str(col),
                "title": f'"{col}" mixes multiple currencies',
                "description": f'Detected {summary}. Values were parsed to numbers but are NOT '
                               f'comparable across currencies — totals mix units. Flagged, not changed.',
                "affected_count": sum(c for _, c in top),
                "examples": [{"row": None, "column": str(col), "from": t, "to": f'{c} value(s)'}
                             for t, c in top],
                "enabled": False, "overridable": [],
            })
        elif info.get("detected_currency"):
            # single-currency: expose the detected code in the convert op description
            for op in operations:
                if op["id"] == f"convert.numeric.{col}":
                    op["description"] += f' · Currency: {info["detected_currency"]}'
                    break

        # CP-16: percent column mixing bare fractions with %-values
        if info.get("is_percent"):
            raw = work_norm[col].dropna().astype(str).str.strip()
            pct = [parse_numeric_value(v) for v in raw[raw.str.endswith('%')]]
            bare = [parse_numeric_value(v) for v in raw[~raw.str.endswith('%')]]
            pct = [x for x in pct if x is not None]
            bare = [x for x in bare if x is not None]
            if pct and bare and max(bare) <= 1.5 and max(pct) > 1.5:
                operations.append({
                    "id": f"quality.mixed_scale.{col}", "category": "quality", "column": str(col),
                    "title": f'"{col}" mixes percentages and fractions',
                    "description": 'Some values are written as "12.5%" (→ 12.5) and others as bare '
                                   'fractions like 0.125 — averaging them mixes scales. Flagged, not '
                                   'changed; make the column consistent at source.',
                    "affected_count": len(bare),
                    "examples": ([{"row": None, "column": str(col), "from": "12.5%", "to": "12.5"}]
                                 + [{"row": None, "column": str(col), "from": "0.125", "to": "0.125 (bare)"}]),
                    "enabled": False, "overridable": [],
                })

    # ── 2c. Excel serial-date candidates (CP-14, OPT-IN / default OFF) ────────
    for col, ctype in type_map.items():
        if col not in work.columns:
            continue
        if ctype not in ("numeric", "identifier"):
            continue
        serial = TypeDetector.detect_excel_serial_dates(work[col])
        if serial:
            ex = serial.get("examples", [])
            ex_txt = "; ".join(f'{s} → {d}' for s, d in ex[:3])
            operations.append({
                "id": f"convert.serial_date.{col}", "category": "conversion", "column": str(col),
                "title": f'Convert "{col}" from Excel date serials to dates?',
                "description": f'These integers look like Excel date serials ({ex_txt}). This is '
                               f'OFF by default — tick it only if this column is really dates, not '
                               f'numbers or IDs.',
                "affected_count": serial.get("count", 0),
                "examples": [{"row": None, "column": str(col), "from": str(s), "to": d} for s, d in ex],
                "enabled": False, "overridable": ["disable"],
            })

    # ── 3. Missing-value proposals (post-conversion; CP-02 + CP-06) ───────────
    for col in work_conv.columns:
        ctype = type_map.get(col, 'unknown')
        sim = convert_sim.get(col)
        missing = int(work_conv[col].isna().sum())
        parse_failures = int(sim["fail_mask"].sum()) if sim is not None else 0
        if missing == 0 and parse_failures == 0:
            continue

        # Example failing cells (original value that couldn't be parsed)
        fail_examples = []
        if sim is not None and parse_failures:
            noun = "a number" if sim["kind"] == "numeric" else "a date"
            for i in work_norm.index[sim["fail_mask"]][:MAX_EXAMPLES]:
                fail_examples.append({
                    "row": int(i) + 2, "column": str(col),
                    "from": str(work_norm.at[i, col]),
                    "to": f"(blank — could not be read as {noun})",
                })

        if ctype == 'categorical' or ctype in ('text', 'unknown'):
            if missing == 0:
                continue
            operations.append({
                "id": f"missing.fill_unknown.{col}", "category": "missing", "column": str(col),
                "title": f'Fill {missing} blank label(s) in "{col}" with "Unknown"',
                "description": "Keeps rows usable in charts without inventing a real category",
                "affected_count": missing,
                "examples": [{"row": int(i) + 2, "column": str(col), "from": None, "to": "Unknown"}
                             for i in work_conv.index[work_conv[col].isna()][:MAX_EXAMPLES]],
                "enabled": True, "overridable": ["disable", "fill_value"],
            })
        elif ctype == 'numeric':
            desc = ("Recommended for amounts: blanks are excluded from totals — no invented "
                    "figures. Change below (e.g. fill with 0) if a blank should count as zero.")
            if parse_failures:
                desc = (f'{parse_failures} value(s) could not be read as numbers and would become '
                        f'blank. ' + desc)
            operations.append({
                "id": f"missing.leave_blank.{col}", "category": "missing", "column": str(col),
                "title": f'Handle {missing} missing/unreadable value(s) in "{col}"',
                "description": desc,
                "affected_count": missing,
                "examples": fail_examples,
                "enabled": True,
                "overridable": ["fill_zero", "fill_value", "drop_rows", "keep_text"],
            })
        elif ctype == 'datetime':
            desc = "Missing dates are left blank; those rows drop out of time charts."
            if parse_failures:
                desc = (f'{parse_failures} value(s) could not be read as dates and would become '
                        f'blank. ' + desc)
            operations.append({
                "id": f"missing.leave_blank.{col}", "category": "missing", "column": str(col),
                "title": f'Handle {missing} missing/unreadable date(s) in "{col}"',
                "description": desc,
                "affected_count": missing,
                "examples": fail_examples,
                "enabled": True,
                "overridable": ["drop_rows", "keep_text"],
            })

    # ── 4. Duplicates (CP-03: counted on the NORMALIZED preview) ──────────────
    dup_mask = work_norm.duplicated(keep='first')
    if dup_mask.any():
        operations.append({
            "id": "duplicates.remove", "category": "duplicates", "column": None,
            "title": f"Remove {int(dup_mask.sum())} exact duplicate row(s)",
            "description": "Rows identical in every column after standardizing labels "
                           "(first occurrence is kept)",
            "affected_count": int(dup_mask.sum()),
            "examples": [{"row": int(i) + 2, "column": "(whole row)",
                          "from": "duplicate of an earlier row", "to": "(row removed)"}
                         for i in work_norm.index[dup_mask][:MAX_EXAMPLES]],
            "enabled": True, "overridable": ["disable"],
        })

    # ── 5. Normalization proposals (case + typos) ────────────────────────────
    for col, rep in _preview_norm.items():
        mappings = rep.get('normalizations', [])
        if not mappings:
            continue
        count = 0
        examples = []
        for m in mappings:
            n = int((work[col].astype(str) == m['from']).sum())
            count += n
            if len(examples) < MAX_EXAMPLES:
                examples.append({"row": None, "column": str(col),
                                 "from": m['from'], "to": m['to'],
                                 "note": ("typo fix" if m['reason'] == 'typo_correction'
                                          else "same word, different case") + f" · {n} cell(s)"})
        operations.append({
            "id": f"normalize.{col}", "category": "normalization", "column": str(col),
            "title": f'Standardize labels in "{col}"',
            "description": f'{len(mappings)} spelling/case variant(s) merged into consistent labels',
            "affected_count": count, "examples": examples,
            "enabled": True, "overridable": ["disable"],
            "mappings": mappings,
        })

    # ── 6. Integrity validations — report-only warnings (CP-17) ───────────────
    try:
        from app.services.data_processing.validations import run_validations
        operations.extend(run_validations(work_conv, type_map))
    except Exception as _ve:
        pass

    return {
        "operations": operations,
        "summary": {
            "total_operations": len(operations),
            "rows": len(df),
            "columns": len(df.columns),
            "type_map": type_map,
        },
    }


def apply_plan(
    df: pd.DataFrame,
    plan: Dict[str, Any],
    selected_ids: List[str],
    overrides: Optional[Dict[str, Dict]] = None,
) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, Any]]:
    """
    Apply only the approved operations, in the canonical order (CP-02/03):
        sanitize → normalize labels → deduplicate → convert types → missing
    Conversion runs BEFORE missing handling so that values which fail to parse
    (e.g. "abc" in a currency column) are caught in the same missing pass and
    never leak into the cleaned output as silent, unaccounted nulls.

    overrides: {operation_id: {"action": ..., "value": ...}} where action ∈
        fill_zero | fill_value | drop_rows | keep_text | separator | disable
    Returns (cleaned_df, actions, report). report["null_reconciliation"] maps
    each column to its {before_convert, parse_failures, filled, final} nulls so
    every remaining null is traceable.
    """
    selected = set(selected_ids)
    overrides = overrides or {}
    actions: Dict[str, str] = {}
    ops = {op["id"]: op for op in plan.get("operations", [])}
    work = df.copy()

    def _is_text(s):
        return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)

    # ── 0. Manual cell fixes (CH-19) ─────────────────────────────────────────
    # Applied FIRST, on the original row positions the user saw in the review
    # (before any row is removed), so "Row 14" means the same cell in both
    # places. The value is the user's literal input — later conversion parses
    # it like any other cell; if it still can't parse, the op's own default
    # behaviour covers it. No value is ever invented: the user typed it.
    manual_edit_counts: Dict[str, int] = {}
    for oid, ov in overrides.items():
        if ov.get("action") != "manual_edits":
            continue
        for edit in ov.get("edits", []):
            row, col, val = edit.get("row"), edit.get("column"), edit.get("value")
            if (col in work.columns and isinstance(row, int)
                    and 0 <= row < len(work)):
                work.iat[row, work.columns.get_loc(col)] = val
                manual_edit_counts[col] = manual_edit_counts.get(col, 0) + 1
    if manual_edit_counts:
        total = sum(manual_edit_counts.values())
        cols = ", ".join(f'"{c}"' for c in manual_edit_counts)
        actions["manual_edits"] = f"Applied {total} manual cell fix(es) in {cols}"

    # ── 1. Sanitation (fixed order) ───────────────────────────────────────────
    if "sanitation.whitespace" in selected and "sanitation.whitespace" in ops:
        for col in work.columns:
            if not _is_text(work[col]):
                continue
            cleaned = (work[col].astype(str)
                       .str.replace('\xa0', ' ', regex=False)
                       .str.replace('​', '', regex=False)
                       .str.replace(r'\s{2,}', ' ', regex=True)
                       .str.strip())
            work[col] = cleaned.where(work[col].notna(), work[col])
        actions["whitespace"] = "Normalized whitespace"

    if "sanitation.sentinels" in selected and "sanitation.sentinels" in ops:
        n = 0
        for col in work.columns:
            if not _is_text(work[col]):
                continue
            mask = work[col].astype(str).str.strip().str.lower().isin(DataCleaner.MISSING_SENTINELS)
            mask &= work[col].notna()
            n += int(mask.sum())
            work.loc[mask, col] = np.nan
        actions["sentinels"] = f"Converted {n} placeholder value(s) to missing"

    if "sanitation.headers" in selected and "sanitation.headers" in ops:
        mask = DataCleaner.detect_header_rows(work)
        work = work[~mask]
        actions["headers"] = f"Removed {int(mask.sum())} repeated header row(s)"

    if "sanitation.empty_rows" in selected and "sanitation.empty_rows" in ops:
        before = len(work)
        work = work.dropna(how='all')
        actions["empty_rows"] = f"Removed {before - len(work)} empty row(s)"

    # Total / Subtotal / footer rows (CP-12) — recomputed at apply time so the
    # mask matches the current (post-header/empty) row set
    if "sanitation.aggregate_rows" in selected and "sanitation.aggregate_rows" in ops:
        agg = DataCleaner.detect_aggregate_rows(work)
        removed = int(agg.sum())
        work = work[~agg]
        actions["aggregate_rows"] = f"Removed {removed} total/subtotal row(s)"

    for op_id in list(selected):
        if op_id.startswith("sanitation.drop_column.") and op_id in ops:
            col = ops[op_id]["column"]
            if col in work.columns:
                work = work.drop(columns=[col])
                actions[f"drop_{col}"] = f'Dropped empty column "{col}"'

    work = work.reset_index(drop=True)

    # ── 2. Normalization (before dedupe so variant-only duplicates collapse) ──
    for op_id, op in ops.items():
        if not op_id.startswith("normalize.") or op_id not in selected:
            continue
        col = op["column"]
        if col not in work.columns:
            continue
        mapping = {m["from"]: m["to"] for m in op.get("mappings", [])}
        if mapping:
            work[col] = work[col].replace(mapping)
            actions[f"normalize_{col}"] = f'Standardized {len(mapping)} label variant(s) in "{col}"'

    # ── 3. Deduplicate (CP-03: after normalization) ───────────────────────────
    if "duplicates.remove" in selected and "duplicates.remove" in ops:
        before = len(work)
        work = work.drop_duplicates(keep='first').reset_index(drop=True)
        actions["duplicates"] = f"Removed {before - len(work)} duplicate row(s)"

    # Snapshot null counts on the final row set, before conversion
    nulls_before_convert = {c: int(work[c].isna().sum()) for c in work.columns}

    # ── 4. Convert types (parse-failure nulls appear here) ────────────────────
    # keep_text override on a column's missing op suppresses its conversion
    keep_text_cols = {
        ops[oid]["column"]
        for oid, ov in overrides.items()
        if ov.get("action") == "keep_text" and oid in ops and ops[oid].get("column")
    }
    for op_id, op in ops.items():
        if op_id not in selected or op["column"] not in work.columns:
            continue
        col = op["column"]
        if col in keep_text_cols:
            actions[f"convert_{col}"] = f'"{col}" kept as text (per your choice)'
            continue
        if op_id.startswith("convert.numeric."):
            # honour a separator choice on an ambiguous column (CP-01)
            sep_ov = None
            for moid, mov in overrides.items():
                if mov.get("action") == "separator" and ops.get(moid, {}).get("column") == col:
                    sep_ov = mov.get("value")
            force_eu = True if sep_ov == "eu" else (False if sep_ov == "us" else None)
            parsed, _ = parse_numeric_series(work[col], force_european=force_eu)
            work[col] = parsed
            actions[f"convert_{col}"] = f'"{col}" converted to numbers'
        elif op_id.startswith("convert.datetime."):
            # honour a day/month choice on an ambiguous column (CP-10)
            day_ov = None
            for moid, mov in overrides.items():
                if mov.get("action") == "dayfirst" and ops.get(moid, {}).get("column") == col:
                    day_ov = mov.get("value")
            if day_ov == "day":
                dayfirst = True
            elif day_ov == "month":
                dayfirst = False
            else:
                dayfirst = TypeDetector.sniff_dayfirst(work[col])
            work[col] = pd.to_datetime(work[col], errors='coerce', dayfirst=dayfirst, format='mixed')
            actions[f"convert_{col}"] = f'"{col}" converted to dates'
        elif op_id.startswith("convert.serial_date."):
            # Excel serial → real date (CP-14, opt-in only)
            nums = pd.to_numeric(work[col], errors='coerce')
            work[col] = pd.to_datetime(nums, unit='D', origin='1899-12-30', errors='coerce')
            actions[f"convert_{col}"] = f'"{col}" converted from Excel serials to dates'

    nulls_after_convert = {c: int(work[c].isna().sum()) for c in work.columns}

    # ── 5. Missing handling (original blanks + parse failures together) ───────
    # Runs LAST so numeric fills write real numbers and every parse-failure
    # null is offered for handling instead of leaking silently (CP-02/CP-06).
    filled_counts: Dict[str, int] = {}
    for op_id, op in ops.items():
        if not op_id.startswith("missing."):
            continue
        col = op["column"]
        if col not in work.columns:
            continue
        ov = overrides.get(op_id, {})
        action = ov.get("action")
        if action == "keep_text":
            continue  # already handled at conversion; no fill
        if action == "fill_zero":
            n = int(work[col].isna().sum())
            work[col] = work[col].fillna(0)
            filled_counts[col] = n
            actions[f"missing_{col}"] = f'Filled {n} missing value(s) in "{col}" with 0'
        elif action == "fill_value":
            n = int(work[col].isna().sum())
            work[col] = work[col].fillna(ov.get("value", "Unknown"))
            filled_counts[col] = n
            actions[f"missing_{col}"] = f'Filled {n} missing value(s) in "{col}" with "{ov.get("value")}"'
        elif action == "drop_rows":
            before = len(work)
            work = work[work[col].notna()].reset_index(drop=True)
            actions[f"missing_{col}"] = f'Dropped {before - len(work)} row(s) with missing "{col}"'
        elif op_id in selected and op_id.startswith("missing.fill_unknown."):
            n = int(work[col].isna().sum())
            work[col] = work[col].fillna("Unknown")
            filled_counts[col] = n
            actions[f"missing_{col}"] = f'Filled {n} missing label(s) in "{col}" with "Unknown"'
        # leave-blank selected without override = intentionally left blank

    # ── Null reconciliation (CP-02): every remaining null accounted for ───────
    reconciliation = {}
    for col in work.columns:
        before = nulls_before_convert.get(col, 0)
        after = nulls_after_convert.get(col, before)
        parse_failures = max(0, after - before)
        final_nulls = int(work[col].isna().sum())
        if before or parse_failures or final_nulls or filled_counts.get(col):
            reconciliation[col] = {
                "nulls_before_convert": before,
                "parse_failures": parse_failures,
                "filled": int(filled_counts.get(col, 0)),
                "final_nulls": final_nulls,
            }

    # ── Applied-ops diff (CP-20): what actually changed, with cell examples ───
    applied_ops = []
    for op in plan.get("operations", []):
        oid = op["id"]
        if op.get("category") == "quality":
            continue                        # warnings never change data
        ov = overrides.get(oid, {})
        acted = (oid in selected) or (ov.get("action") and ov.get("action") != "disable")
        if not acted:
            continue
        entry = {
            "id": oid,
            "title": op.get("title"),
            "category": op.get("category"),
            "column": op.get("column"),
            "affected_count": op.get("affected_count", 0),
            "override": ov.get("action"),
            "examples": (op.get("examples") or [])[:5],
        }
        if ov.get("action") == "manual_edits":
            entry["manual_edit_count"] = len(ov.get("edits", []))
        applied_ops.append(entry)

    report = {
        "null_reconciliation": reconciliation,
        "applied_ops": applied_ops,
        "manual_edits": {c: n for c, n in manual_edit_counts.items()},
    }
    return work, actions, report


# ── Approved-policy persistence & replay (CP-05) ──────────────────────────────

def _policy_file(processed_dir, dataset_id: int, user_id: int) -> Path:
    return Path(processed_dir) / f"user_{user_id}" / f"dataset_{dataset_id}_policy.json"


def save_policy(processed_dir, dataset_id: int, user_id: int,
                selected_ids: List[str], overrides: Dict[str, Dict],
                plan: Dict[str, Any]) -> Path:
    """
    Persist the user's approved cleaning decisions so automatic re-cleans
    (live refresh, connector re-import, scheduled reports) reproduce them
    instead of reverting to defaults.
    """
    summary = {}
    for op in plan.get("operations", []):
        summary[op["id"]] = {
            "category": op.get("category"),
            "column": op.get("column"),
            "kind": _op_kind(op["id"], op.get("column")),
            "title": op.get("title"),
        }
    data = {
        "applied_at": datetime.utcnow().isoformat(),
        "selected_ids": list(selected_ids),
        "overrides": overrides or {},
        "plan_summary": summary,
    }
    fp = _policy_file(processed_dir, dataset_id, user_id)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(data, default=str), encoding="utf-8")
    return fp


def load_policy(processed_dir, dataset_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    fp = _policy_file(processed_dir, dataset_id, user_id)
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def apply_policy(df: pd.DataFrame, policy: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, Any], bool, Dict[str, Any]]:
    """
    Re-apply an approved policy to freshly-fetched data (CP-05).

    Ops are matched to the policy by IDENTITY (kind, column) — not by count,
    since counts differ on new data. Matched ops carry the stored override.
    Structural sanitation ops that are new are auto-applied (harmless), but any
    NEW value-level op (a new column, a brand-new problem) is left unselected
    and flagged so the human reviews it.

    Returns (cleaned_df, actions, report, has_new_value_ops, fresh_plan).
    """
    plan = build_plan(df)
    ops = plan.get("operations", [])

    policy_summary = policy.get("plan_summary", {}) or {}
    policy_selected = set(policy.get("selected_ids", []) or [])
    policy_overrides = policy.get("overrides", {}) or {}

    # policy identities → old op id
    policy_idents: Dict[Tuple[str, Optional[str]], str] = {}
    for old_id, meta in policy_summary.items():
        ident = (meta.get("kind") or _op_kind(old_id, meta.get("column")), meta.get("column"))
        policy_idents[ident] = old_id

    selected_ids: List[str] = []
    new_overrides: Dict[str, Dict] = {}
    has_new_value_ops = False

    for op in ops:
        ident = (_op_kind(op["id"], op.get("column")), op.get("column"))
        old_id = policy_idents.get(ident)
        if old_id is not None:
            if old_id in policy_selected:
                selected_ids.append(op["id"])
            if old_id in policy_overrides:
                new_overrides[op["id"]] = policy_overrides[old_id]
        else:
            # Unseen op. Auto-apply structural sanitation; hold value ops for review.
            if op.get("category") == "sanitation":
                selected_ids.append(op["id"])
            elif op.get("category") in _VALUE_CATEGORIES:
                has_new_value_ops = True

    cleaned, actions, report = apply_plan(df, plan, selected_ids, new_overrides)
    return cleaned, actions, report, has_new_value_ops, plan
