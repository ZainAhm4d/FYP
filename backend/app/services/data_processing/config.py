"""
Central tuning constants for the data-processing pipeline (CP-19).

Every threshold that governs detection/cleaning behaviour lives here with a
one-line rationale, so the knobs are discoverable and consistent instead of
being magic numbers scattered across functions. Import from here; do NOT
re-hardcode these values inline.
(Per-dataset overrides are future work and intentionally out of scope.)
"""

# ── Type detection ────────────────────────────────────────────────────────────
# Fraction of a column's non-null values that must satisfy a type's pattern for
# the column to be classified as that type (numeric / datetime / boolean).
TYPE_DETECT_THRESHOLD = 0.8
# A financial column with a strong currency/percent signal is still numeric even
# if only this fraction parse (a minority of junk cells should be flagged, not
# demote the whole column — see CP-02).
NUMERIC_SIGNAL_MIN_RATIO = 0.6
# Below this unique/row ratio a text column is treated as categorical (else text).
CATEGORICAL_MAX_CARDINALITY = 0.5

# ── Numeric / currency parsing ────────────────────────────────────────────────
# How many values to sample when deciding a column's separator convention and
# currency (whole-column decisions must be stable, never per-cell).
NUMERIC_SAMPLE_SIZE = 500
# A currency token seen on ≥ this fraction of values marks the column as currency.
CURRENCY_SIGNAL_MIN = 0.30
# Each distinct currency token at ≥ this fraction counts toward "mixed currency".
CURRENCY_MIXED_MIN = 0.10
# ≥ this fraction of values ending in "%" marks the column as a percentage.
PERCENT_SIGNAL_MIN = 0.5

# ── Categorical normalisation (case-fold + typo merge) ───────────────────────
# Similarity (difflib ratio) required to treat two labels as the same typo pair.
TYPO_STRICT_CUTOFF = 0.87
# Looser cutoff accepted ONLY when the two labels are the same letters rearranged
# (a transposition like "Norht" ↔ "North").
TYPO_TRANSPOSITION_CUTOFF = 0.75
# Cap on distinct values compared in the O(U²) fuzzy pass, so a high-cardinality
# column can't stall the pipeline (cap² comparisons max).
TYPO_UNIQUE_CAP = 300

# ── Missing values / structural ──────────────────────────────────────────────
# A column is dropped as "effectively empty" only at/above this missing fraction
# (financial-safe: sparse-but-real columns like Discount are kept).
COLUMN_DROP_THRESHOLD = 0.95
# Repeated-header / summary-row label match: fraction of a row's label cells that
# must match the column headers for it to be a repeated header row.
HEADER_ROW_MATCH_RATIO = 0.8

# ── Outlier detection (CP-18) ────────────────────────────────────────────────
# |skewness| above which a column is treated as heavy-tailed and switched off
# plain IQR onto a skew-robust method (log-IQR if all-positive, else MAD).
OUTLIER_SKEW_THRESHOLD = 2.0
# IQR fence multiplier (Tukey's standard 1.5·IQR).
OUTLIER_IQR_MULTIPLIER = 1.5
# Modified z-score cutoff for the MAD method (Iglewicz–Hoaglin recommend 3.5).
OUTLIER_MAD_THRESHOLD = 3.5
# Minimum non-null values before outlier detection runs at all.
OUTLIER_MIN_SAMPLE = 8

# ── Relationship suggestion (CH-09) ──────────────────────────────────────────
# Value-overlap containment (|A∩B| / min(|A|,|B|)) required before a column
# pair is even considered a join candidate — the primary evidence gate.
REL_MIN_CONTAINMENT = 0.5
# Minimum overlapping distinct values (guards against tiny coincidences)…
REL_MIN_MATCHES = 20
# …relaxed to this fraction of the smaller column's distincts when it has
# fewer than REL_SMALL_DISTINCTS values.
REL_SMALL_DISTINCTS = 40
REL_SMALL_MIN_FRACTION = 0.5
# Distinct values sampled per column when computing overlap (bounds cost).
REL_SAMPLE_DISTINCTS = 2000
# Confidence blend weights: containment is the evidence, name similarity only
# assists and must NEVER gate a suggestion on its own.
REL_CONTAINMENT_WEIGHT = 0.7
REL_KEYNESS_WEIGHT = 0.2
REL_NAME_WEIGHT = 0.1
# Columns above this null fraction are excluded from candidate scoring.
REL_MAX_NULL_FRACTION = 0.9
# Uniqueness ratio at/above which a join key side counts as "unique" for
# cardinality inference (1:1 / 1:N / N:M).
REL_UNIQUE_RATIO = 0.99
# A numeric column with FEWER distinct values than this can only be treated
# as a plausible key if its name looks id-like (id/key/code/no/ref/pk/fk) —
# otherwise a small measure column (e.g. "qty_on_hand": 1,2,3,4,5 in a
# 5-row table) trivially hits a 100% unique_ratio just from having few rows,
# and gets mistaken for a real key purely by coincidental range overlap with
# an unrelated real ID column (e.g. "customer_id": 1-10).
REL_MIN_NUMERIC_KEY_DISTINCT = 10
# Small sequential integer ID columns (region_id: 1-5) are near-guaranteed to
# be a value subset of ANY other auto-increment ID column with more rows
# (sale_id: 1-30) purely by coincidence — value overlap alone is unreliable
# evidence for small domains. Below REL_SMALL_DISTINCTS distinct values, also
# require the column names to share some resemblance (after stripping common
# id/key/code tokens) unless the raw names are identical.
REL_MIN_CORE_NAME_SIM_SMALL_DOMAIN = 0.35
# Materializing a join whose projected row count exceeds this multiple of the
# larger input requires explicit confirmation (N:M fan-out guard).
REL_FANOUT_MULTIPLE = 3.0
