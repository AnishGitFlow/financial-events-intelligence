"""
semantic_filter.py - Local semantic similarity engine using sentence-transformers.

Runs 100% offline after a one-time model download (~80MB).
No API keys. No token costs. No rate limits.

How it works:
  1. On first use, downloads "all-MiniLM-L6-v2" (one-time, ~80MB)
  2. Pre-encodes all TARGET_CONCEPTS from config into number vectors
  3. For each LinkedIn post, computes cosine similarity to every concept
  4. Returns the highest similarity score and which concept matched
"""

import numpy as np
from sentence_transformers import SentenceTransformer

from config import TARGET_CONCEPTS, SEMANTIC_THRESHOLD, MAX_CHARS_FOR_LLM

# ── Model (loaded lazily on first call) ───────────────────────────────────────────
_model = None
_concept_embeddings = None
_concept_names = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("[SemanticFilter] Loading local embedding model (one-time download ~80MB on first run)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[SemanticFilter] Model ready.")
    return _model


def _get_concept_embeddings() -> tuple[list[str], np.ndarray]:
    """Return (concept_names, embeddings). Cached after first call."""
    global _concept_embeddings, _concept_names
    if _concept_embeddings is None:
        model = _get_model()
        _concept_names = list(TARGET_CONCEPTS.keys())
        descriptions  = list(TARGET_CONCEPTS.values())
        _concept_embeddings = model.encode(descriptions, convert_to_numpy=True, show_progress_bar=False)
        print(f"[SemanticFilter] Encoded {len(_concept_names)} target concepts.")
    return _concept_names, _concept_embeddings


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Public API ────────────────────────────────────────────────────────────────────

def score_post(text: str) -> tuple[float, str]:
    """
    Compute how semantically close the post is to the target concepts.

    Returns:
        (max_score, matched_concept_name)
        max_score is between 0.0 (no match) and 1.0 (perfect match)
    """
    model = _get_model()
    concept_names, concept_embeddings = _get_concept_embeddings()

    # Truncate to save compute time (semantic meaning is usually in the first 700 chars)
    post_embedding = model.encode(text[:MAX_CHARS_FOR_LLM], convert_to_numpy=True, show_progress_bar=False)

    scores = [_cosine_similarity(post_embedding, ce) for ce in concept_embeddings]
    max_score   = max(scores)
    best_concept = concept_names[scores.index(max_score)]

    return round(max_score, 4), best_concept


def is_relevant(text: str) -> tuple[bool, float, str]:
    """
    Main gate check. Returns (passes, score, matched_concept).

    Usage:
        passes, score, concept = is_relevant(post_text)
        if passes:
            # post is semantically aligned with our target signals
    """
    score, concept = score_post(text)
    return score >= SEMANTIC_THRESHOLD, score, concept
