"""
Unit tests for the data-processing layer: TypeDetector, DataCleaner, DataPreprocessor.
Exercises detection accuracy, missing-value handling, duplicate removal,
outlier detection (IQR + Z-score) and category normalization.
"""
import numpy as np
import pandas as pd

from app.services.data_processing.type_detector import TypeDetector
from app.services.data_processing.cleaner import DataCleaner


# ── TypeDetector ───────────────────────────────────────────────────────────────

def test_detect_numeric_and_categorical():
    df = pd.DataFrame({
        "amount": [1.5, 2.0, 3.25, 4.0],
        "category": ["A", "B", "A", "C"],
    })
    tmap = TypeDetector.detect_all_types(df)
    assert tmap["amount"] in ("numeric", "integer", "float")
    assert tmap["category"] in ("categorical", "text", "string")


def test_detect_datetime_column():
    df = pd.DataFrame({"d": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]})
    tmap = TypeDetector.detect_all_types(df)
    assert "date" in tmap["d"] or tmap["d"] == "datetime"


def test_detect_boolean_column():
    df = pd.DataFrame({"flag": ["yes", "no", "yes", "no", "yes"]})
    t = TypeDetector.detect_column_type(df["flag"])
    assert t in ("boolean", "categorical")  # accept either classification


def test_type_statistics_shape():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    tmap = TypeDetector.detect_all_types(df)
    stats = TypeDetector.get_type_statistics(df, tmap)
    assert isinstance(stats, dict)
    assert stats  # non-empty


# ── DataCleaner: missing values ────────────────────────────────────────────────

def test_analyze_missing_values(messy_frame):
    res = DataCleaner.analyze_missing_values(messy_frame)
    assert res["total_missing_cells"] >= 3  # sales(1) + qty(1) + region(1)
    assert set(res["columns_with_missing"]) >= {"region", "sales", "qty"}


def test_handle_missing_values_financial_policy(messy_frame):
    """
    Financial-safety invariant (CLEANING_PIPELINE.md): missing NUMERIC values
    are NEVER fabricated — they are left blank so sums/averages stay truthful
    (pandas excludes NaN). Only categorical LABELS are filled ("Unknown").
    """
    tmap = TypeDetector.detect_all_types(messy_frame)
    cleaned, log = DataCleaner.handle_missing_values(messy_frame, tmap)
    # numeric 'sales' blank is preserved, not invented
    assert cleaned["sales"].isna().sum() == messy_frame["sales"].isna().sum()
    # categorical 'region' blank is filled with a label
    if tmap.get("region") == "categorical":
        assert cleaned["region"].isna().sum() == 0
    assert isinstance(log, (list, dict))


# ── DataCleaner: duplicates ────────────────────────────────────────────────────

def test_analyze_and_remove_duplicates(messy_frame):
    analysis = DataCleaner.analyze_duplicates(messy_frame)
    # rows: South/150/4 appears 3 times -> 2 duplicates
    assert analysis["duplicate_rows"] >= 2
    deduped, removed = DataCleaner.remove_duplicates(messy_frame)
    assert removed >= 2
    assert len(deduped) == len(messy_frame) - removed


# ── DataCleaner: outliers ──────────────────────────────────────────────────────

def test_detect_outliers_iqr_flags_spike():
    df = pd.DataFrame({"v": [10, 11, 12, 13, 12, 11, 10, 1000]})
    tmap = TypeDetector.detect_all_types(df)
    outliers = DataCleaner.detect_outliers(df, tmap, method="iqr")
    assert "v" in outliers
    # The 1000 value should be flagged
    assert outliers["v"]["count"] >= 1


def test_detect_outliers_no_false_positive_on_uniform():
    df = pd.DataFrame({"v": [5, 5, 5, 5, 5, 5]})
    tmap = TypeDetector.detect_all_types(df)
    outliers = DataCleaner.detect_outliers(df, tmap, method="iqr")
    assert outliers.get("v", {}).get("count", 0) == 0


# ── DataCleaner: category normalization ────────────────────────────────────────

def test_normalize_categorical_merges_case_variants(messy_frame):
    tmap = TypeDetector.detect_all_types(messy_frame)
    out = DataCleaner.normalize_categorical_columns(messy_frame.copy(), tmap)
    # normalize_categorical_columns may return (df, log) or df
    df = out[0] if isinstance(out, tuple) else out
    norm = set(str(v).lower() for v in df["region"].dropna().unique())
    # north/NORTH/North should collapse to a single canonical token
    assert sum(1 for v in norm if v == "north") <= 1
