"""
semantic_filter.py

Semantic filtering has been retired from the active pipeline.
This module remains as a compatibility shim for older imports/tests.
"""


def score_post(text: str) -> tuple[float, str]:
    return 0.0, "Semantic filtering disabled"


def is_relevant(text: str) -> tuple[bool, float, str]:
    return True, 0.0, "Semantic filtering disabled"
