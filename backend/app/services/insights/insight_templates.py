"""
Sentence templates for insight narratives.
All placeholders use Python str.format() named keys.
"""

# ── Trend over time ──────────────────────────────────────────────────────────
PERIOD_SUMMARY   = "Total {metric}: {total:,.2f} across {periods} periods (avg {avg:,.2f}/period)"

TREND_UP_STRONG  = "{metric} surged {pct:.1f}% from {start_label} to {end_label}"
TREND_UP_MILD    = "{metric} grew {pct:.1f}% from {start_label} to {end_label}"
TREND_DOWN_STRONG= "{metric} fell {pct:.1f}% from {start_label} to {end_label}"
TREND_DOWN_MILD  = "{metric} declined {pct:.1f}% from {start_label} to {end_label}"
TREND_STABLE     = "{metric} held steady over {periods} periods (range ±{range_pct:.1f}% of avg)"

PEAK_FINDING     = "Peak at {period}: {value:,.2f} — {pct:.1f}% above average"
TROUGH_FINDING   = "Trough at {period}: {value:,.2f} — {pct:.1f}% below average"
SUDDEN_JUMP      = "Sharpest move: {from_label} -> {to_label} ({pct:+.1f}%)"
ANOMALY_NOTE     = "{metric} spiked {pct:.0f}% above normal at {period} - worth investigating"

# ── Category comparison ──────────────────────────────────────────────────────
CATEGORY_SUMMARY = "{metric} totals {total:,.2f} across {n} categories"
TOP_CATEGORY     = "{category} leads with {value:,.2f} ({pct:.1f}% of total {metric})"
CATEGORY_GAP     = "Runner-up {second} is {gap_pct:.1f}% behind the leader"
CONCENTRATION    = "Top {k} categories account for {pct:.1f}% of all {metric}"

# ── Top-K items ──────────────────────────────────────────────────────────────
TOP_K_SUMMARY    = "{direction} {k} items total {total:,.2f} in {metric}"
TOP_K_WINNER     = "#{rank}: {item} — {value:,.2f} {metric}"
TOP_K_GAP        = "Leader is {gap_x:.1f}× the average of the other top items"

# ── Scatter / correlation ────────────────────────────────────────────────────
CORR_STRONG_POS  = "Strong positive correlation ({corr:.2f}): {y} rises as {x} increases"
CORR_STRONG_NEG  = "Strong negative correlation ({corr:.2f}): {y} falls as {x} increases"
CORR_MOD_POS     = "Moderate positive correlation ({corr:.2f}) between {x} and {y}"
CORR_MOD_NEG     = "Moderate negative correlation ({corr:.2f}) between {x} and {y}"
CORR_WEAK        = "Weak correlation ({corr:.2f}) between {x} and {y} — likely independent"
SCATTER_STATS    = "Avg {x}: {x_mean:,.2f}  |  Avg {y}: {y_mean:,.2f}"

# ── Distribution ─────────────────────────────────────────────────────────────
DIST_SUMMARY     = "{column}: {unique} distinct values across {total} records"
DIST_DOMINANT    = "'{value}' is the most common, appearing in {pct:.1f}% of records"
DIST_NUMERIC     = "{column}: range [{min_v:,.2f} – {max_v:,.2f}], mean {mean:,.2f}, median {median:,.2f}"
DIST_SKEW        = "Distribution is {skew_dir} skewed (mean vs. median diverge by {gap_pct:.1f}%)"
