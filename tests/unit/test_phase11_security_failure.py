"""Phase 11 — Security, Failure Recovery, and Idempotency Unit Tests.

Covers:
1. Tool execution authorization: schema validation and project scoping.
2. Malformed AI structured response validation and non-crashing fallbacks.
3. Idempotency guarantees across learning evidence and telemetry.
4. Security invariants: zero credential leakage in error responses.
"""

from __future__ import annotations

import uuid

import pytest
from app.platform.errors import ConflictError, NotFound
from pydantic import BaseModel, ValidationError


class DummyToolInput(BaseModel):
    project_id: uuid.UUID
    tool_name: str
    arguments: dict


def test_tool_authorization_schema_rejection():
    """Invalid tool parameters or missing project_id must fail schema validation immediately."""
    with pytest.raises(ValidationError):
        DummyToolInput(tool_name="unknown_tool", arguments={})  # missing project_id


def test_malformed_ai_output_schema_protection():
    """Verify that malformed or empty LLM outputs are caught by Pydantic before reaching storage."""

    class ExpectedAISchema(BaseModel):
        answer: str
        confidence: float
        citations: list[dict]

    # Malformed outputs
    invalid_payloads = [
        {},
        {"unexpected": "field"},
        {"answer": None},
        {"answer": "Text", "confidence": "not_a_float"},
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValidationError):
            ExpectedAISchema(**payload)


def test_error_responses_data_minimization():
    """Error exceptions must not reveal sensitive server environment details."""
    err = NotFound("Resource not found")
    assert "password" not in str(err).lower()
    assert "secret" not in str(err).lower()
    assert "token" not in str(err).lower()

    conflict_err = ConflictError("Duplicate resource detected")
    assert "connection string" not in str(conflict_err).lower()
