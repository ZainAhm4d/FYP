"""
Intent Classifier — maps a natural-language query to a QueryTemplateType.

Primary mode:  sentence-transformers (all-MiniLM-L6-v2) with cosine similarity.
Fallback mode: keyword scoring via synonym_manager (no heavy dependencies).

The model and pre-computed template embeddings are loaded once at startup
and cached to disk so subsequent loads are near-instant.
"""
from __future__ import annotations

import logging
import os
import pickle
from typing import Dict, List, Optional, Tuple

from .synonym_manager import INTENT_KEYWORDS, score_intent_keywords

logger = logging.getLogger(__name__)

# Try to import sentence-transformers (optional — falls back to keyword mode)
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning(
        "sentence-transformers not installed — NLP engine running in keyword-only mode. "
        "Install: pip install sentence-transformers  (requires PyTorch CPU build)"
    )

_MODEL_NAME = "all-MiniLM-L6-v2"
_CACHE_PATH = os.path.join(os.path.dirname(__file__), "_models", "intent_embeddings.pkl")

# Example queries per intent type — their centroid embedding is the classification target.
# Keep a diverse set so the centroid is well-centred in embedding space.
INTENT_EXAMPLES: Dict[str, List[str]] = {
    "trend_over_time": [
        "show me the sales trend over time",
        "how has revenue changed month by month",
        "plot monthly revenue over the year",
        "track quantity sold over the past year",
        "show revenue growth over time",
        "display the trend of profit by month",
        "how did sales change each quarter",
        "revenue over time",
        "show me weekly sales history",
        "what is the trend in orders",
    ],
    "category_comparison": [
        "compare revenue by product category",
        "which department has the highest sales",
        "show sales breakdown by region",
        "compare performance across different segments",
        "revenue per category",
        "show me sales by product type",
        "breakdown of revenue by department",
        "bar chart comparing regions",
        "how do different categories compare",
    ],
    "distribution_analysis": [
        "show the distribution of product prices",
        "what is the spread of salaries",
        "histogram of order amounts",
        "how are sales distributed",
        "breakdown of customer ages",
        "show me the frequency of purchase amounts",
        "pie chart of category proportions",
        "how is revenue distributed across ranges",
        "what percentage of orders fall in each range",
    ],
    "top_k_items": [
        "top 5 products by revenue",
        "which are the best performing employees",
        "show top 10 customers by sales",
        "best selling products",
        "highest revenue categories",
        "bottom 5 products by quantity",
        "most profitable items",
        "rank products by total sales",
        "top performers this year",
        "which products have the highest sales",
    ],
    "scatter_relationship": [
        "is there a correlation between price and quantity sold",
        "show the relationship between salary and experience",
        "scatter plot of revenue vs cost",
        "how does age affect salary",
        "plot quantity versus price",
        "correlation between two variables",
        "show me revenue against marketing spend",
        "does price impact quantity",
    ],
}


class IntentClassifier:
    """
    Classifies a natural-language query into one of the five QueryTemplateTypes.

    Usage (module-level singleton pattern):
        from .intent_classifier import classify_intent, preload_model
        preload_model()          # at app startup
        intent, confidence = classify_intent("show top 5 products by sales")
    """

    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._template_embeddings: Optional[Dict[str, object]] = None
        self._mode: str = "keyword"
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load model (or confirm keyword mode). Safe to call multiple times."""
        if self._loaded:
            return
        if EMBEDDINGS_AVAILABLE:
            self._load_embeddings_model()
        else:
            logger.info("IntentClassifier: running in keyword-only mode")
        self._loaded = True

    def classify(self, query_text: str) -> Tuple[str, float]:
        """
        Return (intent_name, confidence).
        confidence is 0..1 (cosine sim for embeddings; normalised keyword score for fallback).
        """
        if not self._loaded:
            self.load()
        if self._mode == "embeddings" and self._model and self._template_embeddings:
            return self._classify_embeddings(query_text)
        return self._classify_keywords(query_text.lower())

    @property
    def mode(self) -> str:
        """'embeddings' or 'keyword'"""
        return self._mode

    # ------------------------------------------------------------------
    # Embeddings path
    # ------------------------------------------------------------------

    def _load_embeddings_model(self) -> None:
        try:
            self._model = SentenceTransformer(_MODEL_NAME)
            self._mode = "embeddings"
            self._template_embeddings = self._load_or_compute_embeddings()
            logger.info("IntentClassifier: loaded %s in embeddings mode", _MODEL_NAME)
        except Exception as exc:
            logger.warning(
                "IntentClassifier: could not load model (%s) — falling back to keyword mode", exc
            )
            self._model = None
            self._mode = "keyword"

    def _load_or_compute_embeddings(self) -> Dict[str, object]:
        import numpy as np  # noqa: PLC0415 — conditional import

        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)

        if os.path.exists(_CACHE_PATH):
            try:
                with open(_CACHE_PATH, "rb") as fh:
                    cached = pickle.load(fh)
                if set(cached.keys()) == set(INTENT_EXAMPLES.keys()):
                    logger.info("IntentClassifier: loaded cached embeddings from %s", _CACHE_PATH)
                    return cached
            except Exception:
                pass  # Recompute on any read error

        logger.info("IntentClassifier: computing template embeddings (first-run only)…")
        embeddings: Dict[str, object] = {}
        for intent, examples in INTENT_EXAMPLES.items():
            vecs = self._model.encode(examples, convert_to_numpy=True, show_progress_bar=False)
            embeddings[intent] = np.mean(vecs, axis=0)  # centroid

        with open(_CACHE_PATH, "wb") as fh:
            pickle.dump(embeddings, fh)
        logger.info("IntentClassifier: saved embeddings cache to %s", _CACHE_PATH)
        return embeddings

    def _classify_embeddings(self, query_text: str) -> Tuple[str, float]:
        import numpy as np  # noqa: PLC0415

        query_vec = self._model.encode(
            [query_text], convert_to_numpy=True, show_progress_bar=False
        )[0]

        best_intent, best_score = "category_comparison", 0.0
        for intent, centroid in self._template_embeddings.items():
            norm = np.linalg.norm(query_vec) * np.linalg.norm(centroid) + 1e-8
            sim = float(np.dot(query_vec, centroid) / norm)
            if sim > best_score:
                best_score = sim
                best_intent = intent

        return best_intent, round(best_score, 4)

    # ------------------------------------------------------------------
    # Keyword fallback path
    # ------------------------------------------------------------------

    def _classify_keywords(self, query_lower: str) -> Tuple[str, float]:
        scores = score_intent_keywords(query_lower)
        if not scores or all(v == 0.0 for v in scores.values()):
            return "category_comparison", 0.0

        best = max(scores, key=lambda k: scores[k])
        total = sum(scores.values())
        confidence = round(scores[best] / total, 4) if total > 0 else 0.0
        return best, confidence


# ---------------------------------------------------------------------------
# Module-level singleton — lazy-loaded on first classify() call
# ---------------------------------------------------------------------------
_classifier = IntentClassifier()


def classify_intent(query_text: str) -> Tuple[str, float]:
    """Classify a plain-English query; returns (intent_name, confidence 0..1)."""
    return _classifier.classify(query_text)


def get_nlp_mode() -> str:
    """Return active NLP mode: 'embeddings' or 'keyword'."""
    if not _classifier._loaded:
        _classifier.load()
    return _classifier.mode


def preload_model() -> None:
    """Call at app startup to avoid slow first-request latency."""
    _classifier.load()
