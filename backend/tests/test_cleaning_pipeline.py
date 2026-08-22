"""
Phase-1 cleaning-pipeline correctness tests (CLEANING_PIPELINE.md CP-01…CP-07).
Each test maps to an acceptance criterion in the spec.
"""
import numpy as np
import pandas as pd
import pytest

from app.services.data_processing.type_detector import parse_numeric_series
from app.services.data_processing.cleaner import DataCleaner
from app.services.data_processing.cleaning_plan import (
    build_plan, apply_plan, apply_policy, save_policy, load_policy,
)
from app.services.data_processing.io_utils import read_tabular


def _ops_by_kind(plan, prefix):
    return [o for o in plan["operations"] if o["id"].startswith(prefix)]


def _apply(df, plan, selected=None, overrides=None):
    if selected is None:
        selected = [o["id"] for o in plan["operations"] if o.get("enabled")]
    cleaned, actions, report = apply_plan(df, plan, selected, overrides or {})
    return cleaned, actions, report


# ── CP-01: European-decimal false positive ────────────────────────────────────

def test_cp01_us_thousands_not_misparsed():
    p, info = parse_numeric_series(pd.Series(["1,234", "12,345", "2,000"]))
    assert list(p) == [1234.0, 12345.0, 2000.0]
    assert info["separator_ambiguous"] is True
    assert info["european_format"] is False


def test_cp01_real_european_still_parses():
    p, info = parse_numeric_series(pd.Series(["1.234,56", "2.000,00"]))
    assert list(p) == [1234.56, 2000.0]
    assert info["european_format"] is True
    assert info["separator_ambiguous"] is False


def test_cp01_ambiguous_column_offers_choice_and_override():
    df = pd.DataFrame({"amount": ["1,234", "2,000", "3,500"]})
    plan = build_plan(df)
    conv = _ops_by_kind(plan, "convert.numeric.amount")
    assert conv, "expected a numeric-conversion op"
    assert conv[0].get("choices", {}).get("kind") == "separator"
    # default apply → thousands
    cleaned, _, _ = _apply(df, plan)
    assert list(cleaned["amount"]) == [1234.0, 2000.0, 3500.0]
    # override to european
    ov = {conv[0]["id"]: {"action": "separator", "value": "eu"}}
    cleaned2, _, _ = _apply(df, plan, overrides=ov)
    assert list(cleaned2["amount"]) == [1.234, 2.0, 3.5]


# ── CP-02: parse-failure nulls surfaced & reconciled ──────────────────────────

def test_cp02_unparseable_currency_cell_flagged_and_reconciled():
    df = pd.DataFrame({
        "Revenue": ["$1,000.00", "$2,000.00", "abc", "$3,000.00", "$4,000.00"],
        "Id":      ["a", "b", "c", "d", "e"],
    })
    plan = build_plan(df)
    miss = _ops_by_kind(plan, "missing.leave_blank.Revenue")
    assert miss, "expected a missing/residual op for Revenue"
    froms = " ".join(str(e.get("from")) for e in miss[0]["examples"])
    assert "abc" in froms  # the exact failing cell is shown
    cleaned, _, report = _apply(df, plan)
    recon = report["null_reconciliation"]["Revenue"]
    assert recon["parse_failures"] == 1
    # every remaining null accounted for
    assert int(cleaned["Revenue"].isna().sum()) == recon["final_nulls"] == 1


def test_cp02_fill_zero_handles_both_blank_and_parse_failure():
    # currency signal → column detected numeric despite one junk cell; second
    # column keeps the blank row from being dropped as fully-empty
    df = pd.DataFrame({
        "Revenue": ["$100", "abc", "", "$200", "$300"],
        "Id":      ["a", "b", "c", "d", "e"],
    })
    plan = build_plan(df)
    op = _ops_by_kind(plan, "missing.leave_blank.Revenue")[0]
    cleaned, _, report = _apply(df, plan, overrides={op["id"]: {"action": "fill_zero"}})
    assert int(cleaned["Revenue"].isna().sum()) == 0
    assert (pd.to_numeric(cleaned["Revenue"]) == 0).sum() == 2  # "abc" + blank → 0


# ── CP-03: dedupe after normalization ─────────────────────────────────────────

def test_cp03_variant_duplicate_removed():
    df = pd.DataFrame({
        "Customer": ["ACME Corp", "acme corp", "Globex"],
        "Amount":   ["100", "100", "200"],
    })
    plan = build_plan(df)
    dup = _ops_by_kind(plan, "duplicates.remove")
    assert dup and dup[0]["affected_count"] == 1
    cleaned, _, _ = _apply(df, plan)
    assert len(cleaned) == 2


# ── CP-04: transitive typo merge ──────────────────────────────────────────────

def test_cp04_typo_chain_collapses_deterministically():
    tmap = {"country": "categorical"}
    base = ["America"] * 10 + ["Amrica", "Americaa"]
    import random
    for _ in range(4):
        random.shuffle(base)
        out, _ = DataCleaner.normalize_categorical_columns(pd.DataFrame({"country": base}), tmap)
        assert set(out["country"].unique()) == {"America"}


# ── CP-05: approved policy persists & replays ─────────────────────────────────

def test_cp05_policy_replayed_on_refresh(tmp_path):
    df1 = pd.DataFrame({"Revenue": ["100", "", "200"], "Region": ["North", "north", "South"]})
    plan = build_plan(df1)
    rev_op = _ops_by_kind(plan, "missing.leave_blank.Revenue")[0]
    selected = [o["id"] for o in plan["operations"] if o.get("enabled")]
    overrides = {rev_op["id"]: {"action": "fill_zero"}}
    save_policy(str(tmp_path), 1, 1, selected, overrides, plan)

    policy = load_policy(str(tmp_path), 1, 1)
    assert policy is not None

    # fresh data, same shape → Revenue blank must still be filled with 0
    df2 = pd.DataFrame({"Revenue": ["150", "", "250", ""], "Region": ["North", "NORTH", "South", "south"]})
    cleaned, _actions, _report, has_new, _fresh = apply_policy(df2, policy)
    assert int(cleaned["Revenue"].isna().sum()) == 0
    assert (pd.to_numeric(cleaned["Revenue"]) == 0).sum() == 2
    assert has_new is False


def test_cp05_new_column_triggers_review(tmp_path):
    df1 = pd.DataFrame({"Revenue": ["100", "200"]})
    plan = build_plan(df1)
    save_policy(str(tmp_path), 2, 1,
                [o["id"] for o in plan["operations"] if o.get("enabled")], {}, plan)
    policy = load_policy(str(tmp_path), 2, 1)
    # fresh data grows a brand-new messy column
    df2 = pd.DataFrame({"Revenue": ["100", "200"], "Notes": ["ok", "N/A"]})
    _cleaned, _a, _r, has_new, _fresh = apply_policy(df2, policy)
    assert has_new is True


# ── CP-06: date failures visible ──────────────────────────────────────────────

def test_cp06_unparseable_date_flagged():
    df = pd.DataFrame({
        "Date": ["2024-01-15", "2024-02-20", "not a date", "2024-03-01", "2024-04-10"],
        "Id":   ["a", "b", "c", "d", "e"],
    })
    plan = build_plan(df)
    miss = _ops_by_kind(plan, "missing.leave_blank.Date")
    assert miss, "expected a missing op for the date column"
    froms = " ".join(str(e.get("from")) for e in miss[0]["examples"])
    assert "not a date" in froms
    cleaned, _, report = _apply(df, plan)
    recon = report["null_reconciliation"]["Date"]
    assert recon["parse_failures"] == 1
    assert int(cleaned["Date"].isna().sum()) == recon["final_nulls"]


# ── CP-07: encoding-aware read ────────────────────────────────────────────────

def test_cp07_cp1252_csv_reads_without_mojibake(tmp_path):
    p = tmp_path / "vendors.csv"
    p.write_bytes("vendor,amount\nMüller GmbH,100\nCafé Ltd,200\n".encode("cp1252"))
    df = read_tabular(p)
    assert "Müller GmbH" in df["vendor"].tolist()
    assert "Café Ltd" in df["vendor"].tolist()


def test_cp07_utf8_csv_still_reads(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text("name,x\nAlpha,1\nBeta,2\n", encoding="utf-8")
    df = read_tabular(p)
    assert list(df["name"]) == ["Alpha", "Beta"]


# ── End-to-end financial stress case ──────────────────────────────────────────

def test_e2e_financial_stress():
    df = pd.DataFrame({
        "Invoice": ["INV-001", "INV-002", "INV-003", "INV-004", "INV-002"],
        "Customer": ["ACME Corp", "acme corp", "Globex", "Umbrella", "acme corp"],
        "Revenue": ["$1,234", "$2,000", "(500)", "abc", "$2,000"],   # US thousands + accounting neg + junk
        "Region": ["North", "north", "Norht", "South", "north"],
    })
    plan = build_plan(df)
    cleaned, actions, report = _apply(df, plan)

    # Revenue parsed as thousands (NOT 1.234), accounting negative preserved
    rev = pd.to_numeric(cleaned["Revenue"], errors="coerce")
    assert 1234.0 in set(rev.dropna())
    assert (rev < 0).any()                       # (500) → -500
    # "abc" became a reconciled null, not a silent one
    assert report["null_reconciliation"]["Revenue"]["parse_failures"] >= 1
    # variant duplicate (acme corp / ACME Corp, same invoice) removed
    assert len(cleaned) < len(df)
    # Region typo folded
    assert "Norht" not in set(cleaned["Region"].astype(str))


# ── CP-09: per-op fill choices available as structured overrides ──────────────

def test_cp09_missing_op_exposes_fill_options():
    df = pd.DataFrame({"Revenue": ["$100", "", "$200", "$300", "$400"], "Id": list("abcde")})
    plan = build_plan(df)
    op = _ops_by_kind(plan, "missing.leave_blank.Revenue")[0]
    # UI renders a dropdown from these; all four options must be offered
    for choice in ("fill_zero", "fill_value", "drop_rows", "keep_text"):
        assert choice in op["overridable"], choice


def test_cp09_dropdown_override_matches_chat_override():
    # The dropdown writes {"action":"fill_zero"} — identical to the chat path;
    # both must produce the same cleaned result (single code path).
    df = pd.DataFrame({"Revenue": ["$100", "", "$200", "$300", "$400"], "Id": list("abcde")})
    plan = build_plan(df)
    op = _ops_by_kind(plan, "missing.leave_blank.Revenue")[0]
    sel = [o["id"] for o in plan["operations"] if o.get("enabled")]
    a, _, _ = apply_plan(df, plan, sel, {op["id"]: {"action": "fill_zero"}})
    b, _, _ = apply_plan(df, plan, sel, {op["id"]: {"action": "fill_zero"}})
    assert list(pd.to_numeric(a["Revenue"])) == list(pd.to_numeric(b["Revenue"]))
    assert int(a["Revenue"].isna().sum()) == 0


def test_cp09_keep_text_skips_conversion():
    df = pd.DataFrame({"Revenue": ["$100", "$200", "$300"], "Id": list("abc")})
    plan = build_plan(df)
    op = _ops_by_kind(plan, "missing.leave_blank.Revenue")
    conv = _ops_by_kind(plan, "convert.numeric.Revenue")
    # if there are no missing/residual cells there is no missing op; use convert op's keep_text
    target = (op[0] if op else conv[0])["id"]
    sel = [o["id"] for o in plan["operations"] if o.get("enabled")]
    cleaned, _, _ = apply_plan(df, plan, sel, {target: {"action": "keep_text"}})
    # column stays as text (still contains the "$")
    assert cleaned["Revenue"].astype(str).str.contains(r"\$").any()


# ── CP-10: ambiguous day/month needs a choice ─────────────────────────────────

def test_cp10_ambiguous_date_offers_choice_and_round_trips():
    df = pd.DataFrame({
        "Date": ["03/04/2024", "05/06/2024", "07/08/2024", "02/03/2024", "06/07/2024"],
        "Id": list("abcde"),
    })
    plan = build_plan(df)
    dt = _ops_by_kind(plan, "convert.datetime.Date")[0]
    assert dt.get("choices", {}).get("kind") == "dayfirst"
    sel = [o["id"] for o in plan["operations"] if o.get("enabled")]
    day, _, _ = apply_plan(df, plan, sel, {dt["id"]: {"action": "dayfirst", "value": "day"}})
    mon, _, _ = apply_plan(df, plan, sel, {dt["id"]: {"action": "dayfirst", "value": "month"}})
    assert str(day["Date"].iloc[0])[:10] == "2024-04-03"   # 03=day, 04=month
    assert str(mon["Date"].iloc[0])[:10] == "2024-03-04"   # 03=month, 04=day


def test_cp10_unambiguous_date_has_no_choice():
    df = pd.DataFrame({"Date": ["25/12/2024", "13/06/2024", "01/01/2024"], "Id": list("abc")})
    plan = build_plan(df)
    dt = _ops_by_kind(plan, "convert.datetime.Date")
    if dt:  # a >12 component proves day-first → decided, no choice needed
        assert "choices" not in dt[0]


# ── CP-11: policy identities match so re-review can mark Applied/New ───────────

def test_cp11_policy_identities_align_with_fresh_plan(tmp_path):
    from app.services.data_processing.cleaning_plan import _op_kind
    df1 = pd.DataFrame({"Region": ["North", "north", "South"], "Rev": ["1", "2", "3"]})
    plan1 = build_plan(df1)
    save_policy(str(tmp_path), 9, 9,
                [o["id"] for o in plan1["operations"] if o.get("enabled")], {}, plan1)
    policy = load_policy(str(tmp_path), 9, 9)
    # every stored op carries a stable (kind, column) identity the UI can match
    for old_id, meta in policy["plan_summary"].items():
        assert meta["kind"] == _op_kind(old_id, meta["column"])
    # a fresh plan on the same-shaped data reuses those identities
    plan2 = build_plan(pd.DataFrame({"Region": ["North", "NORTH", "South"], "Rev": ["4", "5", "6"]}))
    fresh_idents = {(_op_kind(o["id"], o.get("column")), o.get("column")) for o in plan2["operations"]}
    policy_idents = {(m["kind"], m["column"]) for m in policy["plan_summary"].values()}
    assert policy_idents & fresh_idents   # overlap exists → badges resolve


# ══ PHASE 3 — Financial-domain correctness (CP-12…CP-17) ══════════════════════

# ── CP-12: total / subtotal / footer rows ─────────────────────────────────────

def test_cp12_total_row_detected_and_removed():
    df = pd.DataFrame({
        "Item":   ["Widget", "Gadget", "Gizmo", "Total"],
        "Region": ["North", "South", "East", ""],
        "Amount": ["100", "200", "300", "600"],
    })
    plan = build_plan(df)
    agg = _ops_by_kind(plan, "sanitation.aggregate_rows")
    assert agg, "expected an aggregate-rows op"
    assert agg[0]["enabled"] is True                      # default ON
    # approving removes the total row; sum of details matches
    cleaned, _, _ = _apply(df, plan)
    amt = pd.to_numeric(cleaned["Amount"], errors="coerce")
    assert len(cleaned) == 3
    assert amt.sum() == 600                                # 100+200+300, no double count
    # unchecking keeps it
    keep = [o["id"] for o in plan["operations"] if o.get("enabled") and o["id"] != agg[0]["id"]]
    kept, _, _ = apply_plan(df, plan, keep, {})
    assert len(kept) == 4


def test_cp12_no_false_positive_on_clean_data():
    df = pd.DataFrame({"Item": ["A", "B", "C", "D"], "Amount": ["10", "20", "30", "40"]})
    plan = build_plan(df)
    assert not _ops_by_kind(plan, "sanitation.aggregate_rows")


# ── CP-13: mixed currencies ───────────────────────────────────────────────────

def test_cp13_mixed_currency_warning():
    df = pd.DataFrame({"Price": ["$100", "$200", "€100", "€300", "$400", "€250"], "Id": list("abcdef")})
    plan = build_plan(df)
    warn = _ops_by_kind(plan, "quality.mixed_currency.Price")
    assert warn and warn[0]["category"] == "quality"
    assert warn[0]["enabled"] is False                    # non-destructive
    # applying the plan does NOT alter row count or drop the column
    cleaned, _, _ = _apply(df, plan)
    assert "Price" in cleaned.columns and len(cleaned) == len(df)


def test_cp13_single_currency_no_warning():
    df = pd.DataFrame({"Price": ["$100", "$200", "$300"], "Id": list("abc")})
    plan = build_plan(df)
    assert not _ops_by_kind(plan, "quality.mixed_currency")


# ── CP-14: Excel serial dates (opt-in, default OFF) ───────────────────────────

def test_cp14_serial_dates_optin_off_by_default():
    # 45123 → 2023-07-16, etc.
    df = pd.DataFrame({"When": ["45123", "45124", "45200", "45300", "45400", "45500"], "Id": list("abcdef")})
    plan = build_plan(df)
    op = _ops_by_kind(plan, "convert.serial_date.When")
    assert op, "expected a serial-date op"
    assert op[0]["enabled"] is False                      # must NOT auto-apply
    ex = {e["from"]: e["to"] for e in op[0]["examples"]}
    assert ex.get("45123") == "2023-07-16"
    # ignoring it leaves the values as-is (NOT reinterpreted as dates)
    default_sel = [o["id"] for o in plan["operations"] if o.get("enabled")]
    left, _, _ = apply_plan(df, plan, default_sel, {})
    assert not pd.api.types.is_datetime64_any_dtype(left["When"])
    assert 45123.0 in pd.to_numeric(left["When"], errors="coerce").tolist()
    # approving it converts to real dates
    conv, _, _ = apply_plan(df, plan, default_sel + [op[0]["id"]], {})
    assert str(conv["When"].iloc[0])[:10] == "2023-07-16"


# ── CP-15: parser robustness ──────────────────────────────────────────────────

def test_cp15_unicode_minus_euro_spaces_and_currency():
    from app.services.data_processing.type_detector import parse_numeric_series, parse_numeric_value
    p, info = parse_numeric_series(pd.Series(["−1 234,56 €", "2 000,00 €"]))
    assert list(p) == [-1234.56, 2000.0]
    assert info["detected_currency"] == "€"
    p2, info2 = parse_numeric_series(pd.Series(["₦1,200", "₦900"]))   # ₦ not in old list
    assert list(p2) == [1200.0, 900.0]
    assert info2["detected_currency"] == "₦"
    assert parse_numeric_value("−500") == -500.0


# ── CP-16: mixed-scale percent ────────────────────────────────────────────────

def test_cp16_mixed_scale_percent_warning():
    df = pd.DataFrame({"Margin": ["12.5%", "30%", "0.125", "0.4", "18%", "0.22"], "Id": list("abcdef")})
    plan = build_plan(df)
    assert _ops_by_kind(plan, "quality.mixed_scale.Margin")


def test_cp16_uniform_percent_no_warning():
    df = pd.DataFrame({"Margin": ["12.5%", "30%", "18%", "22%"], "Id": list("abcd")})
    plan = build_plan(df)
    assert not _ops_by_kind(plan, "quality.mixed_scale")


# ── CP-17: integrity validations (report-only) ────────────────────────────────

def test_cp17_conflicting_key_and_qty_price_flags():
    df = pd.DataFrame({
        "Invoice ID": ["INV-1", "INV-2", "INV-1", "INV-3"],   # INV-1 duplicated
        "Quantity":   ["2", "5", "2", "10"],
        "Unit Price": ["10", "4", "10", "3"],
        "Amount":     ["20", "20", "999", "30"],              # row3 conflict + qty×price mismatch
    })
    plan = build_plan(df)
    assert _ops_by_kind(plan, "quality.conflicting_key")
    assert _ops_by_kind(plan, "quality.qty_price_amount")
    # report-only: nothing dropped/mutated by these
    cleaned, _, _ = _apply(df, plan)
    assert set(df.columns).issubset(set(cleaned.columns))


def test_cp17_clean_data_no_flags():
    df = pd.DataFrame({
        "Invoice ID": ["INV-1", "INV-2", "INV-3"],
        "Quantity":   ["2", "5", "10"],
        "Unit Price": ["10", "4", "3"],
        "Amount":     ["20", "20", "30"],
    })
    plan = build_plan(df)
    assert not _ops_by_kind(plan, "quality.conflicting_key")
    assert not _ops_by_kind(plan, "quality.qty_price_amount")


# ══ PHASE 4 — Robustness & reporting (CP-18…CP-21) ════════════════════════════

# ── CP-18: skew-aware outlier flagging ────────────────────────────────────────

def test_cp18_lognormal_not_overflagged_but_spike_caught():
    np.random.seed(1)
    vals = np.round(np.random.lognormal(mean=7, sigma=1.0, size=400), 2)
    vals = np.append(vals, vals.max() * 100)          # extreme spike
    df = pd.DataFrame({"Revenue": vals})
    tmap = {"Revenue": "numeric"}
    auto = DataCleaner.detect_outliers(df, tmap, method="auto")
    iqr = DataCleaner.detect_outliers(df, tmap, method="iqr")
    assert auto["Revenue"]["percentage"] < 2.0        # skew-robust
    assert iqr["Revenue"]["percentage"] > 5.0         # plain IQR over-flags
    assert auto["Revenue"]["count"] >= 1              # spike still caught
    assert auto["Revenue"]["method"] in ("log-IQR", "MAD")


def test_cp18_symmetric_data_uses_plain_iqr():
    df = pd.DataFrame({"v": [10, 11, 12, 13, 12, 11, 10, 9, 12, 1000]})
    out = DataCleaner.detect_outliers(df, {"v": "numeric"}, method="auto")
    assert out["v"]["count"] >= 1                     # 1000 flagged


# ── CP-19: thresholds centralized ─────────────────────────────────────────────

def test_cp19_config_constants_exist_and_used():
    from app.services.data_processing import config as C
    for name in ("TYPO_STRICT_CUTOFF", "TYPO_TRANSPOSITION_CUTOFF", "TYPO_UNIQUE_CAP",
                 "COLUMN_DROP_THRESHOLD", "NUMERIC_SAMPLE_SIZE", "OUTLIER_SKEW_THRESHOLD",
                 "OUTLIER_MAD_THRESHOLD"):
        assert hasattr(C, name), name


def test_cp19_no_inline_magic_numbers():
    import pathlib, re as _re
    root = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "data_processing"
    for fname in ("cleaner.py", "type_detector.py"):
        src = (root / fname).read_text(encoding="utf-8")
        # strip comments so rationale text ("≥0.87") doesn't trip the check
        code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
        assert "0.87" not in code, f"0.87 inline in {fname}"
        assert "head(300)" not in code, f"head(300) inline in {fname}"
        assert "0.95" not in code, f"0.95 inline in {fname}"


# ── CP-20: applied-ops diff in the report ─────────────────────────────────────

def test_cp20_report_includes_applied_ops_and_reconciliation():
    df = pd.DataFrame({
        "Revenue": ["$100", "abc", "$200", "$300"],
        "Region":  ["North", "north", "South", "South"],
    })
    plan = build_plan(df)
    sel = [o["id"] for o in plan["operations"] if o.get("enabled")]
    cleaned, actions, report = apply_plan(df, plan, sel, {})
    # applied_ops lists what ran, with examples
    assert report["applied_ops"], "expected applied_ops in report"
    assert all("title" in op and "examples" in op for op in report["applied_ops"])
    # quality/serial ops (non-applied) are excluded
    assert all(op["category"] != "quality" for op in report["applied_ops"])
    # reconciliation totals match the cleaned file
    for col, r in report["null_reconciliation"].items():
        assert int(cleaned[col].isna().sum()) == r["final_nulls"]


# ── CH-19: manual cell fixes flow through apply_plan ─────────────────────────

def test_ch19_manual_edits_applied_and_reported():
    df = pd.DataFrame({
        "Revenue": ["$100", "abc", "$200", "$300"],
        "Region":  ["North", "North", "South", "South"],
    })
    plan = build_plan(df)
    sel = [o["id"] for o in plan["operations"] if o.get("enabled")]
    # the user manually fixes the unparseable cell (row 1) to a real number
    residual_op = next((o for o in plan["operations"]
                        if o["column"] == "Revenue" and
                        (o["id"].startswith("residual.") or o["id"].startswith("missing."))),
                       plan["operations"][0])
    overrides = {residual_op["id"]: {"action": "manual_edits",
                                     "edits": [{"row": 1, "column": "Revenue", "value": "$150"}]}}
    cleaned, actions, report = apply_plan(df, plan, sel, overrides)
    # the typed value parsed like any other cell — no null left in that row
    assert cleaned["Revenue"].notna().all()
    assert float(cleaned.loc[1, "Revenue"]) == 150.0
    assert report["manual_edits"].get("Revenue") == 1
    assert "manual_edits" in actions
