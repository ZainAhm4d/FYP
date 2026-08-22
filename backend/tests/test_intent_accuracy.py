"""
Intent-classification accuracy harness (Phase 2 success criterion: >= 90%).

Runs a labeled set of ~50 natural-language questions spanning all three sample
datasets (ecommerce sales, HR analytics, inventory) through the deterministic,
offline KEYWORD engine (LLM disabled) so the metric is reproducible and does not
depend on an external API. The live LLM path is exercised separately in the API
tests. Prints a per-intent breakdown and asserts overall accuracy >= 90%.
"""
import pytest

from app.services.nlp.intent_classifier import classify_intent

# (question, expected_intent) — drawn from columns across all 3 sample datasets:
#   ecommerce: date, product, category, revenue, quantity
#   hr:        department, position, salary, hire_date, performance_rating, years_of_service
#   inventory: item, category, stock, reorder_level, supplier, unit_cost
LABELED = [
    # ── trend_over_time (10) ──────────────────────────────────────────────────
    ("show sales trend by month", "trend_over_time"),
    ("revenue over time", "trend_over_time"),
    ("monthly revenue trend", "trend_over_time"),
    ("how did sales change over the year", "trend_over_time"),
    ("plot revenue by week", "trend_over_time"),
    ("sales trend across quarters", "trend_over_time"),
    ("revenue growth over time", "trend_over_time"),
    ("salary trend over the years", "trend_over_time"),
    ("show hiring trend by year", "trend_over_time"),
    ("stock levels over time", "trend_over_time"),
    # ── category_comparison (11) ──────────────────────────────────────────────
    ("compare revenue by category", "category_comparison"),
    ("revenue per region", "category_comparison"),
    ("total sales by product category", "category_comparison"),
    ("compare sales across departments", "category_comparison"),
    ("breakdown of revenue by region", "category_comparison"),
    ("sales by category", "category_comparison"),
    ("average salary by department", "category_comparison"),
    ("total stock by supplier", "category_comparison"),
    ("compare unit cost across suppliers", "category_comparison"),
    ("average performance rating by department", "category_comparison"),
    ("revenue by product", "category_comparison"),
    # ── top_k_items (11) ──────────────────────────────────────────────────────
    ("top 5 products by revenue", "top_k_items"),
    ("top 10 customers by sales", "top_k_items"),
    ("highest selling products", "top_k_items"),
    ("bottom 3 products by quantity", "top_k_items"),
    ("which products sell the most", "top_k_items"),
    ("rank products by revenue", "top_k_items"),
    ("top 5 employees by salary", "top_k_items"),
    ("highest paid positions", "top_k_items"),
    ("bottom 5 items by stock", "top_k_items"),
    ("top 3 suppliers by unit cost", "top_k_items"),
    ("lowest stock items", "top_k_items"),
    # ── distribution_analysis (9) ─────────────────────────────────────────────
    ("distribution of prices", "distribution_analysis"),
    ("price distribution", "distribution_analysis"),
    ("frequency of categories", "distribution_analysis"),
    ("histogram of salaries", "distribution_analysis"),
    ("how are ratings distributed", "distribution_analysis"),
    ("distribution of salaries", "distribution_analysis"),
    ("distribution of performance ratings", "distribution_analysis"),
    ("frequency of departments", "distribution_analysis"),
    ("histogram of unit cost", "distribution_analysis"),
    # ── scatter_relationship (9) ──────────────────────────────────────────────
    ("correlation between price and quantity", "scatter_relationship"),
    ("relationship between revenue and quantity", "scatter_relationship"),
    ("scatter plot of price vs sales", "scatter_relationship"),
    ("how does price relate to quantity", "scatter_relationship"),
    ("correlation between salary and years of service", "scatter_relationship"),
    ("relationship between stock and reorder level", "scatter_relationship"),
    ("how does salary relate to performance rating", "scatter_relationship"),
    ("correlation between unit cost and stock", "scatter_relationship"),
    ("revenue vs quantity scatter", "scatter_relationship"),
]


def _run():
    correct, results, per_intent = 0, [], {}
    for q, expected in LABELED:
        intent, conf = classify_intent(q)
        ok = intent == expected
        correct += ok
        results.append((q, expected, intent, conf, ok))
        d = per_intent.setdefault(expected, [0, 0])
        d[1] += 1
        d[0] += ok
    return correct, results, per_intent


def test_intent_accuracy_at_least_90pct(monkeypatch, capsys):
    correct, results, per_intent = _run()
    total = len(results)
    accuracy = correct / total

    lines = [f"\n=== Intent Classification Accuracy (keyword engine) ===",
             f"Overall: {correct}/{total} = {accuracy:.1%}\n",
             "Per-intent:"]
    for intent, (c, n) in sorted(per_intent.items()):
        lines.append(f"  {intent:24s} {c}/{n} = {c/n:.0%}")
    misses = [r for r in results if not r[4]]
    if misses:
        lines.append("\nMisclassified:")
        for q, exp, got, conf, _ in misses:
            lines.append(f"  {q!r}: expected {exp}, got {got} (conf={conf:.2f})")
    report = "\n".join(lines)
    print(report)
    with open("intent_accuracy_report.txt", "w", encoding="utf-8") as fh:
        fh.write(report + "\n")

    assert accuracy >= 0.90, f"Intent accuracy {accuracy:.1%} < 90%\n{report}"
