"""
Type Detection Service
Automatically detects data types for dataset columns.

Financial-aware: currency symbols/codes, accounting negatives "(1,234.50)",
European decimal format "1.234,56", percentages, and thousands separators are
all recognized as numeric — critical for SME/financial exports where amounts
almost never arrive as clean floats.
"""
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from app.services.data_processing import config as C

# ── Currency markers (CP-15) ─────────────────────────────────────────────────
# Known symbols + ISO-4217 codes. This list is only used for *labelling* a
# detected currency and for a fast known-token regex — the value parser strips
# currency generically (any 1–4 char non-numeric edge token), so unlisted
# currencies (₦, R$, zł, CHF, …) still parse. EXTEND freely.
CURRENCY_TOKENS = {
    "$", "£", "€", "₹", "¥", "₩", "₦", "₨", "฿", "₺", "zł", "R$", "Rs", "Rs.", "CHF",
    "USD", "EUR", "GBP", "INR", "PKR", "AED", "SAR", "CAD", "AUD", "JPY", "CNY",
    "NGN", "ZAR", "BRL", "MXN", "CHF", "SGD", "HKD", "NZD", "TRY", "RUB", "KRW",
}
# Fast regex for the known tokens (prefix or suffix), used where a quick strip
# is enough. Longest-first so "Rs." beats "Rs".
_known_sorted = sorted((re.escape(t) for t in CURRENCY_TOKENS), key=len, reverse=True)
_CURRENCY_RE = re.compile(
    r"^\s*(?:" + "|".join(_known_sorted) + r")\s*|"
    r"\s*(?:" + "|".join(_known_sorted) + r")\s*$",
    re.IGNORECASE,
)

# Uppercased known tokens for membership tests (ISO codes / multi-char symbols)
_CURR_UPPER = {t.upper() for t in CURRENCY_TOKENS}
_CURR_UPPER |= {t.upper().rstrip(".") for t in CURRENCY_TOKENS}


def _is_currency_token(tok: Optional[str]) -> bool:
    """
    A token counts as currency only if it is a pure symbol (no ASCII letters,
    e.g. $ € ₦) or a KNOWN alphabetic code (USD, EUR, Rs, CHF). This is what
    stops identifier prefixes like "INV" / "ORD" being mistaken for currency
    and their numbers being extracted (which would wrongly turn an ID column
    numeric).
    """
    if not tok:
        return False
    core = tok.rstrip(".").strip()
    if not core:
        return False
    if not re.search(r"[A-Za-z]", core):        # pure symbol
        return True
    return core.upper() in _CURR_UPPER           # known alphabetic code only


def _currency_token_of(raw) -> Optional[str]:
    """
    Extract a *currency* token (leading or trailing) from one value, or None.
    "$1,234"→"$", "1.234 EUR"→"EUR", "₦900"→"₦", "Rs. 5,000"→"Rs",
    "INV-1"→None (identifier, not currency), "1234"→None.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip().replace("\xa0", " ").replace("−", "-")
    if not s or s.endswith("%"):
        return None
    s = s.lstrip("(").rstrip(")").strip()
    m = re.match(r"^([^\d\s.,()%+\-]{1,4})", s)          # leading symbol/code
    if m and _is_currency_token(m.group(1)):
        return m.group(1)
    m2 = re.search(r"([^\d\s.,()%+\-]{1,4})$", s)        # trailing symbol/code
    if m2 and _is_currency_token(m2.group(1)):
        return m2.group(1)
    return None

# ── Separator-convention evidence regexes (CP-01) ─────────────────────────────
# A single value can be UNAMBIGUOUS evidence for one convention, AMBIGUOUS
# (could be either), or no evidence. We decide the whole column from the
# balance of unambiguous evidence and NEVER guess per-cell.
#
# US thousands-only integer: "1,234" / "12,345" — a comma with a following
# group of exactly 3 digits and NO decimal point. This is ALSO what a naive
# reader would misread as a European decimal, so it is AMBIGUOUS, not euro.
_AMBIG_COMMA_RE = re.compile(r"^-?\d{1,3}(,\d{3})+$")
# Strong EURO evidence: dot-grouped thousands ("1.234" / "1.234.567,89").
# A US number never uses dots as thousands separators.
_EURO_DOTGROUP_RE = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")
# EURO decimal: a comma followed by 1–2 digits at the end ("12,5" / "0,75").
# US thousands always come in groups of 3, so 1–2 trailing digits are euro.
_EURO_DECIMAL_RE = re.compile(r"^-?\d+,\d{1,2}$")
# Strong US evidence: a dot used as the decimal point ("12.5" / "1,234.56").
_US_DECIMAL_RE = re.compile(r"^-?\d{1,3}(,\d{3})*\.\d+$|^-?\d+\.\d+$")


def parse_numeric_value(raw, european: bool = False) -> Optional[float]:
    """
    Parse one messy financial value to float. Returns None if unparseable.

    Handles: "$1,234.56", "(500.00)" accounting negative, "1 234", "12.5%",
    "1.234,56" (european=True), "Rs. 5,000", trailing minus "1234-",
    unicode minus "−500" (CP-15), euro-mode spaces "1 234,56", and arbitrary
    currency tokens ("₦1,200", "1 234,56 €") via generic edge stripping.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return float(raw)

    # Normalize unicode minus (U+2212) and non-breaking space up front
    s = str(raw).strip().replace("\xa0", " ").replace("−", "-")
    if not s:
        return None

    negative = False
    # Accounting negative: (1,234.50)
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    # Trailing minus: 1234-
    if s.endswith("-") and not s.startswith("-"):
        negative = True
        s = s[:-1].strip()

    is_percent = s.endswith("%")
    if is_percent:
        s = s[:-1].strip()

    # Strip a currency prefix/suffix — but ONLY if it is real currency, not an
    # identifier prefix like "INV-" (which would wrongly yield 1 from "INV-1").
    m = re.match(r"^([^\d]*)(\d.*)$", s)
    if not m:
        return None
    lead, s = m.group(1), m.group(2)
    if "-" in lead:
        negative = True
    lead_core = re.sub(r"[\s.\-()]", "", lead)
    if lead_core and re.search(r"[A-Za-z]", lead_core) and lead_core.upper() not in _CURR_UPPER:
        return None                    # identifier prefix (INV, ORD…), not a number
    # trailing token
    tm = re.search(r"\d([^\d]*)$", s)
    trail = tm.group(1) if tm else ""
    trail_core = re.sub(r"[\s.\-()%]", "", trail)
    if trail_core and re.search(r"[A-Za-z]", trail_core) and trail_core.upper() not in _CURR_UPPER:
        return None                    # trailing identifier suffix, not a number
    s = re.sub(r"[^\d]*$", "", s)      # trailing currency / spaces
    if not s:
        return None

    # Normalize separators (strip spaces in BOTH conventions — CP-15)
    if european:
        s = s.replace(" ", "").replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "").replace(" ", "")

    try:
        value = float(s)
    except ValueError:
        return None

    if negative:
        value = -abs(value)
    return value


def _decimal_evidence(value_no_currency: str) -> str:
    """
    Classify one already-currency-stripped token as separator evidence:
    'euro' | 'us' | 'ambiguous' | 'none'. (CP-01)
    """
    v = value_no_currency
    if _EURO_DOTGROUP_RE.match(v) or _EURO_DECIMAL_RE.match(v):
        return "euro"
    if _US_DECIMAL_RE.match(v):
        return "us"
    if _AMBIG_COMMA_RE.match(v):
        return "ambiguous"
    return "none"


def parse_numeric_series(series: pd.Series, force_european: Optional[bool] = None) -> Tuple[pd.Series, Dict]:
    """
    Parse a whole column of messy numeric strings.

    The comma/dot convention is decided ONCE for the whole column from the
    balance of unambiguous evidence — never per-cell (mixed conventions in one
    column would silently corrupt magnitudes 1000×). US thousands-only integers
    like "1,234" are treated as AMBIGUOUS, not European decimals (CP-01).

    force_european overrides auto-detection (used to honour a user's separator
    choice on an ambiguous column).

    Returns (parsed_float_series, info) where info includes:
    { parsed_ratio, is_currency, is_percent, european_format,
      accounting_negatives, separator_ambiguous, ambiguous_examples }
    """
    non_null = series.dropna().astype(str).str.strip()
    non_null = non_null[non_null != ""]
    if len(non_null) == 0:
        return pd.Series(np.nan, index=series.index), {
            "parsed_ratio": 0.0, "separator_ambiguous": False,
        }

    sample = non_null.head(C.NUMERIC_SAMPLE_SIZE)

    # Tally separator evidence + currency tokens per value
    euro_ev = us_ev = ambig_ev = 0
    ambiguous_examples: List[str] = []
    currency_counter: Counter = Counter()
    for raw in sample:
        tok = _currency_token_of(raw)
        if tok:
            currency_counter[tok] += 1
        # strip currency token + noise so the separator classifier sees the number
        token = str(raw).replace("−", "-")
        if tok:
            token = token.replace(tok, "", 1)
        token = token.replace("%", "").replace("(", "").replace(")", "").strip()
        token = token.strip("-").strip()   # sign is irrelevant to separator convention
        token = token.replace(" ", "")     # space thousands ("1 234,56") — strip for classify
        kind = _decimal_evidence(token)
        if kind == "euro":
            euro_ev += 1
        elif kind == "us":
            us_ev += 1
        elif kind == "ambiguous":
            ambig_ev += 1
            if len(ambiguous_examples) < 3:
                ambiguous_examples.append(str(raw))

    separator_ambiguous = False
    if force_european is not None:
        european = bool(force_european)
    elif euro_ev > 0 and us_ev == 0:
        european = True                       # unambiguous euro evidence
    elif us_ev > 0 and euro_ev == 0:
        european = False                      # unambiguous US evidence
    elif euro_ev > 0 and us_ev > 0:
        european = False                      # conflicting → default US (comma=thousands)
    else:
        # No decimal-point evidence either way. If comma-grouped integers are
        # present, the column is genuinely ambiguous — default to US thousands
        # (statistically far more common) but flag for a user decision.
        european = False
        separator_ambiguous = ambig_ev > 0

    percent_hits = sum(v.endswith("%") for v in sample)
    paren_hits = sum(v.startswith("(") and v.endswith(")") for v in sample)

    # Currency detection (CP-13/CP-15): a token seen on ≥30% of values marks
    # the column as currency; ≥2 distinct tokens (each ≥10%) = mixed currencies.
    n = len(sample)
    currencies = {t: int(c) for t, c in currency_counter.items()}
    total_curr = sum(currencies.values())
    significant = {t: c for t, c in currencies.items() if c / n >= C.CURRENCY_MIXED_MIN}
    dominant = max(currencies, key=currencies.get) if currencies else None
    detected_currency = dominant if (dominant and currencies[dominant] / n >= C.CURRENCY_SIGNAL_MIN) else None
    mixed_currency = len(significant) >= 2

    parsed = series.map(lambda v: parse_numeric_value(v, european=european))
    parsed = pd.to_numeric(parsed, errors="coerce")
    parsed_ratio = parsed.notna().sum() / max(len(non_null), 1)

    info = {
        "parsed_ratio": round(float(min(parsed_ratio, 1.0)), 4),
        "is_currency": (total_curr / n >= C.CURRENCY_SIGNAL_MIN) or bool(detected_currency),
        "is_percent": percent_hits / len(sample) >= C.PERCENT_SIGNAL_MIN,
        "european_format": european,
        "accounting_negatives": int(paren_hits),
        "separator_ambiguous": bool(separator_ambiguous),
        "ambiguous_examples": ambiguous_examples,
        "currencies": currencies,
        "detected_currency": detected_currency,
        "mixed_currency": bool(mixed_currency),
    }
    return parsed, info


class TypeDetector:
    """
    Detects and categorizes column data types in datasets
    """
    
    # Common date formats to try
    DATE_FORMATS = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%Y-%m-%d %H:%M:%S',
        '%m/%d/%Y %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
    ]
    
    @staticmethod
    def detect_column_type(series: pd.Series, threshold: float = C.TYPE_DETECT_THRESHOLD) -> str:
        """
        Detect the type of a single column
        
        Args:
            series: Pandas Series to analyze
            threshold: Minimum ratio of valid values to determine type
        
        Returns:
            Type string: 'numeric', 'categorical', 'datetime', 'boolean', 'text', or 'unknown'
        """
        # Handle empty series
        if len(series) == 0 or series.isna().all():
            return 'unknown'
        
        # Drop NA values for type detection
        non_null_series = series.dropna()
        if len(non_null_series) == 0:
            return 'unknown'
        
        # Check if already datetime
        if pd.api.types.is_datetime64_any_dtype(series):
            return 'datetime'
        
        # Check if numeric
        if pd.api.types.is_numeric_dtype(series):
            # Check if boolean (all values are 0 or 1)
            unique_vals = series.dropna().unique()
            if len(unique_vals) <= 2 and set(unique_vals).issubset({0, 1, True, False}):
                return 'boolean'
            return 'numeric'
        
        # For object types, try to infer type
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            # Try datetime detection
            if TypeDetector._is_datetime_column(non_null_series, threshold):
                return 'datetime'
            
            # Check for boolean-like strings
            if TypeDetector._is_boolean_column(non_null_series, threshold):
                return 'boolean'
            
            # Check if it's actually numeric stored as string
            if TypeDetector._is_numeric_string(non_null_series, threshold):
                return 'numeric'
            
            # Determine if categorical or text based on cardinality
            unique_vals = non_null_series.unique()
            cardinality_ratio = len(unique_vals) / len(non_null_series)
            
            # If low cardinality (< 50% unique values), consider categorical
            if cardinality_ratio < C.CATEGORICAL_MAX_CARDINALITY:
                return 'categorical'
            
            # If text is long (avg length > 50 chars), consider as text
            avg_length = non_null_series.astype(str).str.len().mean()
            if avg_length > 50:
                return 'text'
            
            return 'categorical'
        
        return 'unknown'
    
    @staticmethod
    def _is_datetime_column(series: pd.Series, threshold: float) -> bool:
        """Check if column contains datetime values"""
        successful_parses = 0
        total = len(series)
        
        # Try parsing a sample
        sample_size = min(100, total)
        sample = series.sample(n=sample_size) if total > sample_size else series
        
        for val in sample:
            if pd.isna(val):
                continue

            # Try each date format against THIS value specifically — a bare
            # "successful_parses == 0" check here would test the running
            # total across the whole sample, not whether this one value
            # failed, so the pandas fallback below would silently stop
            # running after the very first strict-format hit anywhere in
            # the sample. That under-counts genuinely valid dates in any
            # format not in DATE_FORMATS (e.g. a column mixing "25/02/2025",
            # "01-08-25" and "2025-01-15" — real formats, just not all
            # explicitly listed) enough to push a real date column below
            # the detection threshold and misclassify it as categorical.
            parsed_this_value = False
            for date_format in TypeDetector.DATE_FORMATS:
                try:
                    datetime.strptime(str(val), date_format)
                    parsed_this_value = True
                    break
                except (ValueError, TypeError):
                    continue

            # Pandas' flexible parser as a fallback for formats not in the
            # explicit list above — tried per value, not just once overall.
            if not parsed_this_value:
                try:
                    pd.to_datetime(val)
                    parsed_this_value = True
                except Exception:
                    pass

            if parsed_this_value:
                successful_parses += 1

        return (successful_parses / sample_size) >= threshold
    
    @staticmethod
    def _is_boolean_column(series: pd.Series, threshold: float) -> bool:
        """Check if column contains boolean-like values"""
        boolean_values = {
            'true', 'false', 't', 'f', 
            'yes', 'no', 'y', 'n',
            '1', '0',
            'true', 'false',
            'TRUE', 'FALSE',
            'Yes', 'No',
            'YES', 'NO'
        }
        
        unique_vals = set(series.astype(str).str.strip().unique())
        
        # Check if all unique values are boolean-like
        return len(unique_vals) <= 2 and unique_vals.issubset(boolean_values)
    
    @staticmethod
    def _is_numeric_string(series: pd.Series, threshold: float) -> bool:
        """
        Check if column contains numeric values stored as strings.
        Financial-aware: "$1,234.56", "(500)", "1.234,56", "12.5%" all count.

        A minority of unparseable junk ("abc" in a Revenue column) should NOT
        stop the column being recognized as numeric — otherwise those junk
        cells never get flagged (CP-02). So a strong financial-format signal
        (currency / percent / European / accounting negatives) lowers the bar.
        """
        try:
            _, info = parse_numeric_series(series)
            r = info.get("parsed_ratio", 0)
            if r >= threshold:
                return True
            has_signal = (info.get("is_currency") or info.get("is_percent")
                          or info.get("european_format") or info.get("accounting_negatives"))
            return bool(r >= C.NUMERIC_SIGNAL_MIN_RATIO and has_signal)
        except Exception:
            return False

    @staticmethod
    def sniff_dayfirst_state(series: pd.Series) -> str:
        """
        Decide day-first vs month-first for slash/dash dates by evidence,
        returning one of: 'dayfirst' | 'monthfirst' | 'ambiguous' (CP-10).

        A first component > 12 proves day-first; a second component > 12 proves
        month-first. When NO value disambiguates (every component ≤ 12, e.g.
        "03/04/2024") the convention is genuinely ambiguous and the user must
        decide — we never silently assume US month-first.

        Columns with no slash/dash date tokens at all return 'monthfirst'
        (harmless default; ISO 'YYYY-MM-DD' is order-independent anyway).
        """
        pat = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.]\d{2,4}")
        first_gt12 = second_gt12 = matched = 0
        for val in series.dropna().astype(str).head(200):
            m = pat.match(val.strip())
            if not m:
                continue
            matched += 1
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                first_gt12 += 1
            if b > 12:
                second_gt12 += 1
        if first_gt12 > 0 and second_gt12 == 0:
            return "dayfirst"
        if second_gt12 > 0 and first_gt12 == 0:
            return "monthfirst"
        if first_gt12 > 0 and second_gt12 > 0:
            return "monthfirst"   # conflicting evidence → default, non-ambiguous
        # No slash/dash tokens with a >12 component:
        return "ambiguous" if matched > 0 else "monthfirst"

    @staticmethod
    def sniff_dayfirst(series: pd.Series) -> bool:
        """Backward-compatible boolean: True only when evidence proves day-first."""
        return TypeDetector.sniff_dayfirst_state(series) == "dayfirst"

    # Excel stores dates as day counts from 1899-12-30. 25569 = 1970-01-01,
    # 73050 = 2099-12-31 — the plausible "these integers are really dates" band.
    EXCEL_SERIAL_MIN = 25569
    EXCEL_SERIAL_MAX = 73050

    @staticmethod
    def detect_excel_serial_dates(series: pd.Series) -> Optional[Dict]:
        """
        Heuristic for a column of Excel date serials like 45123 (CP-14).
        Returns {count, examples:[(serial, 'YYYY-MM-DD')...]} or None.

        Deliberately conservative AND surfaced as an OPT-IN op (default OFF):
        plain large integers (counts, IDs) can fall in the same range, so we
        never auto-convert — we only propose.
        """
        if pd.api.types.is_datetime64_any_dtype(series):
            return None
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) < 5:
            return None
        # must be (near-)integers
        if not bool(np.all(np.isclose(np.mod(s.to_numpy(dtype=float), 1.0), 0.0, atol=1e-9))):
            return None
        in_range = float(((s >= TypeDetector.EXCEL_SERIAL_MIN) &
                          (s <= TypeDetector.EXCEL_SERIAL_MAX)).mean())
        if in_range < 0.9:
            return None
        try:
            conv = pd.to_datetime(s, unit="D", origin="1899-12-30", errors="coerce")
        except Exception:
            return None
        if float(conv.isna().mean()) > 0.1:
            return None
        examples = []
        for idx in list(s.index)[:3]:
            d = conv.loc[idx]
            if pd.notna(d):
                examples.append((int(s.loc[idx]), d.strftime("%Y-%m-%d")))
        return {"count": int(len(s)), "examples": examples}
    
    @staticmethod
    def detect_all_types(df: pd.DataFrame) -> Dict[str, str]:
        """
        Detect types for all columns in a DataFrame
        
        Args:
            df: DataFrame to analyze
        
        Returns:
            Dictionary mapping column names to detected types
        """
        type_map = {}

        for column in df.columns:
            type_map[column] = TypeDetector.detect_column_type(df[column])

        return type_map

    @staticmethod
    def detect_all_types_ex(df: pd.DataFrame) -> Tuple[Dict[str, str], Dict[str, Dict]]:
        """
        Like detect_all_types, but also returns per-column format info for
        numeric columns (currency / percentage / European format / accounting
        negatives) so the cleaning report can explain what was recognized.
        """
        type_map = TypeDetector.detect_all_types(df)
        format_info = {}
        for column, col_type in type_map.items():
            if col_type == 'numeric' and not pd.api.types.is_numeric_dtype(df[column]):
                try:
                    _, info = parse_numeric_series(df[column])
                    if info.get('is_currency') or info.get('is_percent') \
                       or info.get('european_format') or info.get('accounting_negatives'):
                        format_info[column] = info
                except Exception:
                    pass
        return type_map, format_info
    
    @staticmethod
    def get_type_statistics(df: pd.DataFrame, type_map: Dict[str, str]) -> Dict[str, any]:
        """
        Get statistics about detected types
        
        Args:
            df: DataFrame
            type_map: Dictionary of column types
        
        Returns:
            Statistics dictionary
        """
        type_counts = {}
        for col_type in type_map.values():
            type_counts[col_type] = type_counts.get(col_type, 0) + 1
        
        return {
            'total_columns': len(df.columns),
            'type_counts': type_counts,
            'type_map': type_map,
            'numeric_columns': [col for col, t in type_map.items() if t == 'numeric'],
            'categorical_columns': [col for col, t in type_map.items() if t == 'categorical'],
            'datetime_columns': [col for col, t in type_map.items() if t == 'datetime'],
            'boolean_columns': [col for col, t in type_map.items() if t == 'boolean'],
            'text_columns': [col for col, t in type_map.items() if t == 'text'],
        }
    
    @staticmethod
    def convert_types(df: pd.DataFrame, type_map: Dict[str, str]) -> pd.DataFrame:
        """
        Convert DataFrame columns to detected types
        
        Args:
            df: DataFrame to convert
            type_map: Dictionary of column types
        
        Returns:
            DataFrame with converted types
        """
        df_converted = df.copy()
        
        for column, col_type in type_map.items():
            if column not in df_converted.columns:
                continue
            
            try:
                if col_type == 'numeric':
                    if pd.api.types.is_numeric_dtype(df_converted[column]):
                        pass  # already clean
                    else:
                        # Financial-aware parse (currency, accounting negatives,
                        # European decimals, percentages, thousands separators)
                        parsed, _info = parse_numeric_series(df_converted[column])
                        df_converted[column] = parsed

                elif col_type == 'datetime':
                    dayfirst = TypeDetector.sniff_dayfirst(df_converted[column])
                    df_converted[column] = pd.to_datetime(
                        df_converted[column], errors='coerce',
                        dayfirst=dayfirst, format='mixed',
                    )
                
                elif col_type == 'boolean':
                    # Convert common boolean representations
                    bool_map = {
                        'true': True, 'false': False, 't': True, 'f': False,
                        'yes': True, 'no': False, 'y': True, 'n': False,
                        '1': True, '0': False,
                        'TRUE': True, 'FALSE': False,
                        'Yes': True, 'No': False,
                        'YES': True, 'NO': False
                    }
                    df_converted[column] = df_converted[column].astype(str).str.strip().map(bool_map)
                
                elif col_type == 'categorical':
                    df_converted[column] = df_converted[column].astype('category')
            
            except Exception as e:
                # If conversion fails, keep original type
                print(f"Warning: Could not convert column {column} to {col_type}: {str(e)}")
                continue
        
        return df_converted
