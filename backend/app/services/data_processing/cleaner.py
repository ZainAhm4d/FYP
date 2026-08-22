"""
Data Cleaning Service
Handles missing values, duplicates, and data quality issues
"""
import re
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime
from difflib import get_close_matches

from app.services.data_processing import config as C

# Total / subtotal / grand-total footer labels (CP-12). Anchored to the end so
# the cell is essentially JUST the total word (+ optional colon) — this avoids
# flagging a company literally named "Total Quality Inc".
_TOTAL_LABEL_RE = re.compile(r"^\s*(grand\s+)?(sub[\s-]?)?total\b[\s:]*$", re.IGNORECASE)


class DataCleaner:
    """
    Cleans and preprocesses dataset according to best practices
    """

    # Sentinel strings that mean "missing" in real-world exports (case-insensitive).
    # Includes Excel error codes, which are endemic in SME financial workbooks.
    MISSING_SENTINELS = {
        '', '-', '--', '?', 'n/a', 'n\\a', 'na', 'null', 'none', 'nil', 'nan',
        '#n/a', '#ref!', '#value!', '#div/0!', '#num!', '#name?', '#null!',
    }

    @staticmethod
    def detect_aggregate_rows(df: pd.DataFrame) -> pd.Series:
        """
        Flag Total / Subtotal / footer rows that would double-count in every
        aggregate (CP-12). Returns a boolean mask over df.index. Detection is
        data-driven — no column names are hardcoded:
          (a) a text cell matches a total-label pattern while the row's other
              label cells are (mostly) empty, OR
          (b) the row's numeric cells each ≈ the sum of the rows above (±0.5%).
        """
        mask = pd.Series(False, index=df.index)
        if len(df) < 3:
            return mask

        def _is_text(s):
            return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)

        # Coerce with the FINANCIAL parser so "$1,054" / "(500)" count as numbers
        from app.services.data_processing.type_detector import parse_numeric_series
        text_cols = [c for c in df.columns if _is_text(df[c])]
        numeric = pd.DataFrame(index=df.index)
        for c in df.columns:
            if pd.api.types.is_numeric_dtype(df[c]):
                numeric[c] = df[c]
            else:
                parsed, _ = parse_numeric_series(df[c])
                numeric[c] = parsed
        numeric_cols = [c for c in df.columns if numeric[c].notna().mean() > 0.5]

        # (a) label-based. A genuine footer has a "Total"-ish LABEL and its other
        # populated cells are NUMBERS (the totals), not more text labels. Numeric
        # cells are excluded from the "other label" tally so numbers-stored-as-text
        # (pre-conversion) don't hide the pattern.
        # Vectorized (per-column pandas string ops, not a Python-level per-row
        # loop) — a `for i in df.index: row = df.loc[i]` loop here took ~27s
        # on a 250k-row dataset, holding the GIL that whole time and stalling
        # every other request/thread in the process, not just this one.
        if text_cols:
            label_count = pd.Series(0, index=df.index)
            total_match_count = pd.Series(0, index=df.index)
            for c in text_cols:
                col = df[c]
                is_label = col.notna() & (col.astype(str).str.strip() != "") & numeric[c].isna()
                is_total = is_label & col.astype(str).str.match(_TOTAL_LABEL_RE)
                label_count += is_label.astype(int)
                total_match_count += is_total.astype(int)
            mask |= (total_match_count >= 1) & (label_count == total_match_count)

        # (b) sum-based — ONLY the last row (a grand-total footer sits at the end).
        # Checking earlier rows risks flagging a detail row that coincidentally
        # equals the running sum (e.g. 300 == 100+200).
        if numeric_cols and len(df) >= 4:
            i = list(df.index)[-1]
            if not mask[i]:
                above = numeric.iloc[:-1]
                above = above[~mask.loc[above.index]]
                if len(above) >= 2:
                    checked = matched = 0
                    for c in numeric_cols:
                        val = numeric.at[i, c]
                        colsum = above[c].sum()
                        if pd.isna(val) or colsum == 0:
                            continue
                        checked += 1
                        if abs(val - colsum) <= abs(colsum) * 0.005:
                            matched += 1
                    if checked >= 1 and matched == checked:
                        mask[i] = True
        return mask

    @staticmethod
    def detect_header_rows(df: pd.DataFrame) -> pd.Series:
        """
        Flag rows that duplicate the column headers (stitched exports) — a
        row where 80%+ of its non-null cells (min 2) equal a column name.

        Vectorized (per-column pandas string ops), not a Python-level
        `df.apply(fn, axis=1)` loop — that loop took ~30s+ on a 250k-row
        dataset (it, and detect_aggregate_rows's old per-row loop, were the
        main reason a large upload's background analysis could hold the GIL
        long enough to stall unrelated requests, including a small upload
        started right after).
        """
        if len(df) == 0 or len(df.columns) == 0:
            return pd.Series(False, index=df.index)

        col_names = {str(c).strip().lower() for c in df.columns}
        hits = pd.Series(0, index=df.index)
        nonnull = pd.Series(0, index=df.index)
        for c in df.columns:
            col = df[c]
            is_nonnull = col.notna()
            normalized = col.astype(str).str.strip().str.lower()
            hits += (is_nonnull & normalized.isin(col_names)).astype(int)
            nonnull += is_nonnull.astype(int)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = hits / nonnull.replace(0, np.nan)
        return (nonnull > 0) & (ratio >= 0.8) & (hits >= 2)

    @staticmethod
    def sanitize_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, any]]:
        """
        Pre-clean structural junk before any type detection runs. Handles the
        realities of Excel/ERP exports:
          - non-breaking / zero-width spaces, stray whitespace, doubled spaces
          - sentinel missing tokens ("N/A", "-", "#DIV/0!", …) -> real NaN
          - repeated header rows (stitched exports)
          - fully empty rows, and empty "Unnamed: N" spreadsheet columns
        Returns (clean_df, actions).
        """
        actions = {}
        df = df.copy()

        # 1) Whitespace hygiene on text columns
        # (pandas 3.x infers strings as 'str' dtype, not object — check both)
        def _is_text(s):
            return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)

        cells_touched = 0
        for col in df.columns:
            if not _is_text(df[col]):
                continue
            original = df[col]
            cleaned = (original.astype(str)
                       .str.replace('\xa0', ' ', regex=False)     # non-breaking space
                       .str.replace('\u200b', '', regex=False)    # zero-width space
                       .str.replace(r'\s{2,}', ' ', regex=True)   # doubled spaces
                       .str.strip())
            cleaned = cleaned.where(original.notna(), original)   # keep real NaN
            changed = (cleaned != original.astype(str)) & original.notna()
            cells_touched += int(changed.sum())
            df[col] = cleaned
        if cells_touched:
            actions['whitespace'] = f'Normalized whitespace in {cells_touched} cells'

        # 2) Sentinel missing tokens -> NaN
        sentinel_count = 0
        for col in df.columns:
            if not _is_text(df[col]):
                continue
            mask = df[col].astype(str).str.strip().str.lower().isin(DataCleaner.MISSING_SENTINELS)
            mask &= df[col].notna()
            if mask.any():
                sentinel_count += int(mask.sum())
                df.loc[mask, col] = np.nan
        if sentinel_count:
            actions['missing_sentinels'] = (
                f'Converted {sentinel_count} placeholder values '
                f'("N/A", "-", Excel error codes, …) to missing'
            )

        # 3) Repeated header rows (row values equal the column names)
        col_names = [str(c).strip().lower() for c in df.columns]
        def _is_header_row(row):
            vals = [str(v).strip().lower() for v in row if pd.notna(v)]
            if not vals:
                return False
            hits = sum(v in col_names for v in vals)
            return hits / len(vals) >= C.HEADER_ROW_MATCH_RATIO and hits >= 2
        header_mask = df.apply(_is_header_row, axis=1)
        if header_mask.any():
            df = df[~header_mask]
            actions['repeated_headers'] = f'Removed {int(header_mask.sum())} repeated header row(s)'

        # 4) Fully empty rows
        empty_rows = df.isna().all(axis=1).sum()
        if empty_rows:
            df = df.dropna(how='all')
            actions['empty_rows'] = f'Removed {int(empty_rows)} completely empty row(s)'

        # 5) Junk columns: unnamed spreadsheet columns that are (near-)empty,
        #    and columns that are 100% empty regardless of name
        junk_cols = []
        for col in df.columns:
            missing_pct = df[col].isna().mean() if len(df) else 1.0
            if missing_pct == 1.0:
                junk_cols.append(col)
            elif str(col).startswith('Unnamed:') and missing_pct >= C.COLUMN_DROP_THRESHOLD:
                junk_cols.append(col)
        if junk_cols:
            df = df.drop(columns=junk_cols)
            actions['junk_columns'] = f'Dropped empty column(s): {", ".join(map(str, junk_cols))}'

        df = df.reset_index(drop=True)
        return df, actions

    @staticmethod
    def analyze_missing_values(df: pd.DataFrame) -> Dict[str, any]:
        """
        Analyze missing values in the dataset
        
        Args:
            df: DataFrame to analyze
        
        Returns:
            Dictionary with missing value statistics
        """
        total_cells = df.shape[0] * df.shape[1]
        missing_cells = df.isna().sum().sum()
        missing_percentage = (missing_cells / total_cells) * 100 if total_cells > 0 else 0
        
        columns_with_missing = {}
        for column in df.columns:
            missing_count = df[column].isna().sum()
            if missing_count > 0:
                columns_with_missing[column] = {
                    'count': int(missing_count),
                    'percentage': round((missing_count / len(df)) * 100, 2)
                }
        
        return {
            'total_missing_cells': int(missing_cells),
            'missing_percentage': round(missing_percentage, 2),
            'columns_affected': len(columns_with_missing),
            'columns_with_missing': columns_with_missing
        }
    
    @staticmethod
    def analyze_duplicates(df: pd.DataFrame) -> Dict[str, any]:
        """
        Analyze duplicate rows in the dataset
        
        Args:
            df: DataFrame to analyze
        
        Returns:
            Dictionary with duplicate statistics
        """
        duplicate_count = df.duplicated().sum()
        duplicate_percentage = (duplicate_count / len(df)) * 100 if len(df) > 0 else 0
        
        return {
            'duplicate_rows': int(duplicate_count),
            'duplicate_percentage': round(duplicate_percentage, 2),
            'unique_rows': int(len(df) - duplicate_count)
        }
    
    @staticmethod
    def handle_missing_values(
        df: pd.DataFrame,
        type_map: Dict[str, str],
        strategy: str = 'auto',
        threshold: float = 0.5
    ) -> Tuple[pd.DataFrame, Dict[str, str]]:
        """
        Handle missing values based on column types and strategy
        
        Args:
            df: DataFrame to clean
            type_map: Dictionary of column types
            strategy: 'auto', 'drop', 'impute_mean', 'impute_median', 'impute_mode'
            threshold: Drop columns if missing_percentage > threshold * 100
        
        Returns:
            Tuple of (cleaned_df, actions_taken)
        """
        df_clean = df.copy()
        actions = {}
        
        # Analyze missing values first
        missing_analysis = DataCleaner.analyze_missing_values(df)
        
        if strategy == 'drop':
            # Drop all rows with any missing values
            rows_before = len(df_clean)
            df_clean = df_clean.dropna()
            rows_dropped = rows_before - len(df_clean)
            actions['strategy'] = f'Dropped {rows_dropped} rows with missing values'
        
        elif strategy == 'auto':
            # Type-aware handling. Guiding principle for BI on financial/SME
            # data: NEVER fabricate figures. Imputing a median into a Revenue
            # column distorts every SUM and trend downstream; a missing amount
            # must stay missing (pandas aggregations exclude NaN correctly).
            # Only labels (categoricals) are safe to fill.
            drop_threshold = max(threshold, C.COLUMN_DROP_THRESHOLD)   # drop only near-empty columns

            for column in list(df_clean.columns):
                missing_count = int(df_clean[column].isna().sum())
                missing_pct = missing_count / len(df_clean) if len(df_clean) else 0

                # Drop column only if it is essentially empty (junk)
                if missing_pct >= drop_threshold:
                    df_clean = df_clean.drop(columns=[column])
                    actions[column] = f'Dropped ({missing_pct:.0%} missing — effectively empty)'
                    continue

                if missing_count == 0:
                    continue

                col_type = type_map.get(column, 'unknown')

                if col_type == 'numeric':
                    # Left missing on purpose — sums/averages stay truthful.
                    actions[column] = (
                        f'{missing_count} missing value(s) left blank — '
                        f'excluded from calculations, never invented'
                    )

                elif col_type == 'categorical':
                    df_clean[column] = df_clean[column].fillna('Unknown')
                    actions[column] = f'{missing_count} missing label(s) filled with "Unknown"'

                elif col_type == 'datetime':
                    # A fabricated date corrupts every time-series bucket.
                    actions[column] = (
                        f'{missing_count} missing date(s) left blank — '
                        f'rows excluded from time-based charts'
                    )

                elif col_type == 'boolean':
                    actions[column] = f'{missing_count} missing value(s) left blank'

                else:
                    # Free text / unknown
                    df_clean[column] = df_clean[column].fillna('Unknown')
                    actions[column] = f'{missing_count} missing value(s) filled with "Unknown"'
        
        elif strategy == 'impute_mean':
            for column in df_clean.columns:
                if type_map.get(column) == 'numeric':
                    mean_val = df_clean[column].mean()
                    df_clean[column] = df_clean[column].fillna(mean_val)
                    actions[column] = f'Filled with mean ({mean_val:.2f})'
        
        elif strategy == 'impute_median':
            for column in df_clean.columns:
                if type_map.get(column) == 'numeric':
                    median_val = df_clean[column].median()
                    df_clean[column] = df_clean[column].fillna(median_val)
                    actions[column] = f'Filled with median ({median_val:.2f})'
        
        elif strategy == 'impute_mode':
            for column in df_clean.columns:
                mode_val = df_clean[column].mode()
                if len(mode_val) > 0:
                    df_clean[column] = df_clean[column].fillna(mode_val[0])
                    actions[column] = f'Filled with mode ({mode_val[0]})'
        
        return df_clean, actions
    
    @staticmethod
    def remove_duplicates(df: pd.DataFrame, keep: str = 'first') -> Tuple[pd.DataFrame, int]:
        """
        Remove duplicate rows
        
        Args:
            df: DataFrame to clean
            keep: 'first', 'last', or False (remove all duplicates)
        
        Returns:
            Tuple of (cleaned_df, rows_removed)
        """
        rows_before = len(df)
        df_clean = df.drop_duplicates(keep=keep)
        rows_removed = rows_before - len(df_clean)
        
        return df_clean, rows_removed
    
    # ── Outlier methods (CP-18) — flag-only, never remove ─────────────────────
    @staticmethod
    def _iqr_mask(series: pd.Series):
        """Tukey IQR fence. Returns (mask, meta) or (None, None) for a constant column."""
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return None, None
        lo = q1 - C.OUTLIER_IQR_MULTIPLIER * iqr
        hi = q3 + C.OUTLIER_IQR_MULTIPLIER * iqr
        return (series < lo) | (series > hi), {"method": "IQR", "bounds": {"lower": float(lo), "upper": float(hi)}}

    @staticmethod
    def _log_iqr_mask(series: pd.Series):
        """IQR on log-transformed values — robust for right-skewed (revenue-like) data."""
        logs = np.log(series.astype(float))
        q1, q3 = logs.quantile(0.25), logs.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return None, None
        lo = q1 - C.OUTLIER_IQR_MULTIPLIER * iqr
        hi = q3 + C.OUTLIER_IQR_MULTIPLIER * iqr
        return (logs < lo) | (logs > hi), {"method": "log-IQR",
                                           "bounds": {"lower": float(np.exp(lo)), "upper": float(np.exp(hi))}}

    @staticmethod
    def _mad_mask(series: pd.Series):
        """Median Absolute Deviation modified z-score (Iglewicz–Hoaglin)."""
        median = series.median()
        mad = (series - median).abs().median()
        if mad == 0:
            return None, None
        modified_z = 0.6745 * (series - median) / mad
        return modified_z.abs() > C.OUTLIER_MAD_THRESHOLD, {
            "method": "MAD", "threshold": C.OUTLIER_MAD_THRESHOLD, "median": float(median)}

    @staticmethod
    def detect_outliers(df: pd.DataFrame, type_map: Dict[str, str], method: str = 'auto') -> Dict[str, List]:
        """
        Flag (never remove) outliers in numeric columns. CP-18: method is chosen
        PER COLUMN by skewness so heavy-tailed financial data isn't over-flagged:
          |skew| > threshold and all-positive → log-IQR
          |skew| > threshold otherwise        → MAD (median absolute deviation)
          else                                → plain IQR (Tukey fence)
        Pass method='iqr'/'mad'/'log_iqr'/'zscore' to force one. The method used
        is recorded per column in the report.
        """
        outliers = {}

        for column in df.columns:
            if type_map.get(column) != 'numeric':
                continue

            series = pd.to_numeric(df[column], errors='coerce').dropna()
            if len(series) < C.OUTLIER_MIN_SAMPLE:
                continue

            if method == 'zscore':
                from scipy import stats
                z = np.abs(stats.zscore(series))
                mask = pd.Series(z > 3, index=series.index)
                meta = {"method": "Z-Score", "threshold": 3}
            else:
                chosen = method
                if method == 'auto':
                    try:
                        skew = float(series.skew())
                    except Exception:
                        skew = 0.0
                    if abs(skew) > C.OUTLIER_SKEW_THRESHOLD:
                        chosen = 'log_iqr' if (series > 0).all() else 'mad'
                    else:
                        chosen = 'iqr'
                if chosen == 'log_iqr' and (series > 0).all():
                    mask, meta = DataCleaner._log_iqr_mask(series)
                elif chosen == 'mad':
                    mask, meta = DataCleaner._mad_mask(series)
                else:
                    mask, meta = DataCleaner._iqr_mask(series)
                if mask is None:      # constant column
                    continue

            # mask is indexed like `series` (non-null rows); count on df length
            count = int(mask.sum())
            if count > 0:
                entry = {
                    'count': count,
                    'percentage': round((count / len(df)) * 100, 2),
                }
                entry.update(meta)
                outliers[column] = entry

        return outliers
    
    @staticmethod
    def normalize_categorical_columns(
        df: pd.DataFrame,
        type_map: Dict[str, str],
        fix_case: bool = True,
        fix_typos: bool = True,
        typo_threshold: float = 0.8
    ) -> Tuple[pd.DataFrame, Dict[str, Dict]]:
        """
        Normalize categorical columns by fixing case sensitivity and typos
        
        Args:
            df: DataFrame to normalize
            type_map: Dictionary mapping column names to their types
            fix_case: Whether to normalize case (converts to Title Case)
            fix_typos: Whether to fix potential typos using fuzzy matching
            typo_threshold: Similarity threshold for fuzzy matching (0.0-1.0)
        
        Returns:
            Tuple of (normalized_df, normalization_report)
        """
        df_normalized = df.copy()
        report = {}
        
        # Find categorical columns (dimensions)
        categorical_columns = [
            col for col, dtype in type_map.items()
            if dtype == 'categorical' and col in df.columns
        ]
        
        # Also check for string columns not in type_map
        for col in df.columns:
            if col not in type_map and (
                pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])
            ):
                categorical_columns.append(col)
        
        for column in categorical_columns:
            try:
                # Skip if column has too many unique values (likely IDs / free
                # text, not categories). Cardinality is measured on CASE-FOLDED
                # values — otherwise case variants ("North"/"NORTH") inflate the
                # count and the columns most in need of normalization get skipped.
                non_null = df_normalized[column].dropna().astype(str)
                if len(non_null) == 0:
                    continue
                folded_unique = non_null.str.casefold().str.strip().nunique()
                if folded_unique > len(non_null) * 0.8:
                    continue
                
                # Get non-null unique values
                unique_values = df_normalized[column].dropna().unique()
                if len(unique_values) == 0:
                    continue
                
                column_changes = {
                    'original_unique_count': len(unique_values),
                    'normalizations': []
                }

                # Step 1: Case normalization — merge values that differ ONLY by
                # case, using the MOST FREQUENT original spelling as canonical.
                # (Never force Title Case: it corrupts "USD"→"Usd", "IBM"→"Ibm",
                # SKU codes, and country/currency codes.)
                if fix_case:
                    counts = df_normalized[column].dropna().value_counts()
                    groups = {}
                    for val, cnt in counts.items():
                        groups.setdefault(str(val).casefold(), []).append((str(val), int(cnt)))

                    value_mapping = {}
                    for _key, variants in groups.items():
                        if len(variants) <= 1:
                            continue
                        # Canonical = most frequent spelling; on a tie prefer a
                        # Title-Case-looking variant ("Unpaid" over "UNPAID"),
                        # never inventing a spelling that wasn't in the data.
                        canonical = max(variants, key=lambda t: (t[1], t[0].istitle()))[0]
                        for variant, _cnt in variants:
                            if variant != canonical:
                                value_mapping[variant] = canonical
                                column_changes['normalizations'].append({
                                    'from': variant,
                                    'to': canonical,
                                    'reason': 'case_normalization'
                                })
                    if value_mapping:
                        df_normalized[column] = df_normalized[column].replace(value_mapping)

                # Step 2: Typo correction — TRANSITIVE via connected components
                # (CP-04). An edge is created between two values only when a
                # merge is safe. All of these must hold for an edge:
                #   - both values ≥ 4 chars (short codes like "Q1"/"Q2" are off-limits)
                #   - identical digit content ("Region 1" ≠ "Region 2", "2023" ≠ "2024")
                #   - high similarity (≥0.87), OR same letters rearranged
                #     (transpositions like "Norht"→"North") with similarity ≥0.75
                #   - frequency asymmetry: the rarer of the pair occurs at most
                #     half as often as the commoner (real typos are rare) — this
                #     stops two legitimately-common categories from being linked
                # Every value in a connected component then maps to the single
                # highest-count member, so chains (A→B→C) collapse to one
                # canonical and the result is independent of iteration order.
                if fix_typos:
                    import re as _re
                    counts = df_normalized[column].dropna().value_counts()
                    # O(U²) fuzzy pass — cap unique values so a high-cardinality
                    # column can't stall the pipeline (cap² comparisons max)
                    if len(counts) > C.TYPO_UNIQUE_CAP:
                        counts = counts.head(C.TYPO_UNIQUE_CAP)
                    values = [str(v) for v in counts.index]
                    count_of = {str(v): int(c) for v, c in counts.items()}
                    digits_of = lambda s: _re.sub(r'\D', '', s)
                    letters_of = lambda s: sorted(s.casefold().replace(' ', ''))

                    # Union-find over the values
                    parent = {v: v for v in values}
                    def _find(x):
                        while parent[x] != x:
                            parent[x] = parent[parent[x]]
                            x = parent[x]
                        return x
                    def _union(a, b):
                        ra, rb = _find(a), _find(b)
                        if ra != rb:
                            parent[rb] = ra

                    # Compare on CASE-FOLDED spellings so "north"/"Norht" match
                    # despite the capital; map back to the original spelling.
                    # (After case-normalization above, each casefold is unique,
                    # so this mapping is 1:1.)
                    long_values = [v for v in values if len(v) >= 4]
                    cf_to_orig = {v.casefold(): v for v in long_values}
                    cf_keys = list(cf_to_orig.keys())
                    for value in long_values:
                        cfv = value.casefold()
                        candidates = [k for k in cf_keys if k != cfv]
                        strict = get_close_matches(cfv, candidates, n=1,
                                                   cutoff=max(typo_threshold, C.TYPO_STRICT_CUTOFF))
                        loose = get_close_matches(cfv, candidates, n=1, cutoff=C.TYPO_TRANSPOSITION_CUTOFF)
                        match_cf = None
                        if strict:
                            match_cf = strict[0]
                        elif loose and sorted(loose[0].replace(' ', '')) == sorted(cfv.replace(' ', '')):
                            match_cf = loose[0]   # transposition typo
                        if not match_cf:
                            continue
                        match = cf_to_orig[match_cf]
                        if digits_of(value) != digits_of(match):
                            continue
                        vc, mc = count_of.get(value, 0), count_of.get(match, 0)
                        # rarer must be ≤ half the commoner (typo asymmetry)
                        if min(vc, mc) * 2 > max(vc, mc):
                            continue
                        _union(value, match)

                    # Canonical per component = highest count
                    # (tie-break: Title-Case-looking, then longest spelling)
                    comp_members: Dict[str, list] = {}
                    for v in values:
                        comp_members.setdefault(_find(v), []).append(v)

                    typo_mapping = {}
                    for members in comp_members.values():
                        if len(members) <= 1:
                            continue
                        canonical = max(
                            members,
                            key=lambda m: (count_of.get(m, 0), m.istitle(), len(m)),
                        )
                        for m in members:
                            if m != canonical:
                                typo_mapping[m] = canonical
                                column_changes['normalizations'].append({
                                    'from': m,
                                    'to': canonical,
                                    'reason': 'typo_correction',
                                })

                    if typo_mapping:
                        df_normalized[column] = df_normalized[column].replace(typo_mapping)
                
                # Update final unique count
                column_changes['normalized_unique_count'] = df_normalized[column].nunique()
                column_changes['changes_made'] = len(column_changes['normalizations'])
                
                if column_changes['changes_made'] > 0:
                    report[column] = column_changes
                    
            except Exception as e:
                print(f"Error normalizing column {column}: {str(e)}")
                continue
        
        return df_normalized, report
    
    @staticmethod
    def generate_cleaning_report(
        df_original: pd.DataFrame,
        df_cleaned: pd.DataFrame,
        type_map: Dict[str, str],
        actions_taken: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Generate comprehensive cleaning report
        
        Args:
            df_original: Original DataFrame
            df_cleaned: Cleaned DataFrame
            type_map: Dictionary of column types
            actions_taken: Dictionary of cleaning actions
        
        Returns:
            Comprehensive cleaning report
        """
        # Original statistics
        original_stats = {
            'rows': len(df_original),
            'columns': len(df_original.columns),
            'missing_cells': int(df_original.isna().sum().sum()),
            'duplicates': int(df_original.duplicated().sum())
        }
        
        # Cleaned statistics
        cleaned_stats = {
            'rows': len(df_cleaned),
            'columns': len(df_cleaned.columns),
            'missing_cells': int(df_cleaned.isna().sum().sum()),
            'duplicates': int(df_cleaned.duplicated().sum())
        }
        
        # Calculate improvements
        rows_removed = original_stats['rows'] - cleaned_stats['rows']
        columns_removed = original_stats['columns'] - cleaned_stats['columns']
        missing_cells_fixed = original_stats['missing_cells'] - cleaned_stats['missing_cells']
        duplicates_removed = original_stats['duplicates'] - cleaned_stats['duplicates']
        
        return {
            'original': original_stats,
            'cleaned': cleaned_stats,
            'improvements': {
                'rows_removed': rows_removed,
                'columns_removed': columns_removed,
                'missing_cells_fixed': missing_cells_fixed,
                'duplicates_removed': duplicates_removed
            },
            'actions_taken': actions_taken,
            'cleaning_timestamp': datetime.utcnow().isoformat(),
            'success': True
        }
