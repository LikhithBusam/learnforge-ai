"""Phase 4 Unit Tests — Query Preprocessing & Multilingual Text Handling.

Verifies:
1. Whitespace normalization and length boundaries.
2. Complete preservation of Unicode / Arabic / mixed scripts (Prompt §10).
3. Rejection of empty / whitespace-only queries.
"""

from __future__ import annotations

import pytest
from app.knowledge.retrieval import preprocess_query
from app.platform.errors import ValidationError


def test_preprocess_query_normalizes_whitespace():
    raw = "   Explain   TCP   congestion    control.  \n\n  "
    result = preprocess_query(raw)
    assert result == "Explain TCP congestion control."


def test_preprocess_query_preserves_arabic_multilingual():
    """Prompt §10: Must preserve Arabic Unicode without destructive ASCII/lowercasing."""
    arabic_query = "ما هي خوارزمية التحكم في الازدحام؟"
    result = preprocess_query(arabic_query)
    assert result == arabic_query

    mixed_query = "اشرح مفهوم TCP window size بالتفصيل"
    result = preprocess_query(mixed_query)
    assert result == mixed_query


def test_preprocess_query_truncates_at_max_chars():
    long_query = "a" * 1200
    result = preprocess_query(long_query, max_chars=1000)
    assert len(result) == 1000


def test_preprocess_query_empty_raises_validation_error():
    with pytest.raises(ValidationError, match="Query cannot be empty"):
        preprocess_query("")

    with pytest.raises(ValidationError, match="Query cannot be empty"):
        preprocess_query("   \n\t  ")
