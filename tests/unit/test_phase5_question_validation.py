"""Unit tests — Question generation schema validation (Phase 5).

Tests: MCQGenerationPayload and OpenEndedGenerationPayload validation.
These are purely Pydantic model validations — no I/O or AI calls.
"""

from __future__ import annotations

import pytest
from app.assessment.schemas import (
    MCQGenerationPayload,
    MCQOption,
    OpenEndedGenerationPayload,
)
from pydantic import ValidationError


class TestMCQGenerationPayload:
    def _valid_payload(self) -> dict:
        return {
            "question_type": "mcq",
            "difficulty": "medium",
            "question": "Which of the following correctly describes CSMA/CD?",
            "options": [
                {"id": "A", "text": "Carrier Sense Multiple Access with Collision Detection"},
                {"id": "B", "text": "A routing algorithm for networks"},
                {"id": "C", "text": "A compression format for data"},
                {"id": "D", "text": "A hardware interface standard"},
            ],
            "correct_option": "A",
            "explanation": "CSMA/CD stands for Carrier Sense Multiple Access with Collision Detection.",
            "source_chunk_ids": ["chunk-001"],
        }

    def test_valid_mcq_accepted(self):
        payload = MCQGenerationPayload.model_validate(self._valid_payload())
        assert payload.correct_option == "A"
        assert len(payload.options) == 4

    def test_duplicate_option_ids_rejected(self):
        data = self._valid_payload()
        data["options"] = [
            {"id": "A", "text": "First option"},
            {"id": "A", "text": "Duplicate A"},  # duplicate id
            {"id": "C", "text": "Third option"},
            {"id": "D", "text": "Fourth option"},
        ]
        with pytest.raises(ValidationError, match="unique"):
            MCQGenerationPayload.model_validate(data)

    def test_duplicate_option_texts_rejected(self):
        data = self._valid_payload()
        data["options"] = [
            {"id": "A", "text": "Same text"},
            {"id": "B", "text": "same text"},  # same after strip+lower
            {"id": "C", "text": "Third option"},
            {"id": "D", "text": "Fourth option"},
        ]
        with pytest.raises(ValidationError, match="unique"):
            MCQGenerationPayload.model_validate(data)

    def test_correct_option_not_in_options_rejected(self):
        data = self._valid_payload()
        data["correct_option"] = "E"  # E is not in options AND not valid A-D
        with pytest.raises(ValidationError):
            MCQGenerationPayload.model_validate(data)

    def test_wrong_number_of_options_rejected(self):
        data = self._valid_payload()
        data["options"] = [
            {"id": "A", "text": "Only three options"},
            {"id": "B", "text": "Second option"},
            {"id": "C", "text": "Third option"},
        ]
        with pytest.raises(ValidationError):
            MCQGenerationPayload.model_validate(data)

    def test_missing_source_chunk_ids_rejected(self):
        data = self._valid_payload()
        data["source_chunk_ids"] = []
        with pytest.raises(ValidationError):
            MCQGenerationPayload.model_validate(data)

    def test_question_too_short_rejected(self):
        data = self._valid_payload()
        data["question"] = "Short?"
        with pytest.raises(ValidationError):
            MCQGenerationPayload.model_validate(data)

    def test_invalid_difficulty_rejected(self):
        data = self._valid_payload()
        data["difficulty"] = "impossible"
        with pytest.raises(ValidationError):
            MCQGenerationPayload.model_validate(data)

    def test_all_valid_difficulties_accepted(self):
        data = self._valid_payload()
        for d in ("easy", "medium", "hard"):
            data["difficulty"] = d
            payload = MCQGenerationPayload.model_validate(data)
            assert payload.difficulty.value == d


class TestOpenEndedGenerationPayload:
    def _valid_payload(self) -> dict:
        return {
            "question_type": "open_ended",
            "difficulty": "hard",
            "question": "Explain how CSMA/CD resolves collisions in an Ethernet network.",
            "reference_answer": (
                "When a collision is detected, stations send a 32-bit jam signal and "
                "use binary exponential backoff to delay retransmission. The backoff "
                "window doubles with each successive collision, reducing re-collision probability."
            ),
            "rubric": [
                {"criterion": "Describes collision detection mechanism", "weight": 0.4},
                {"criterion": "Explains jam signal", "weight": 0.3},
                {"criterion": "Describes binary exponential backoff", "weight": 0.3},
            ],
            "source_chunk_ids": ["chunk-001"],
        }

    def test_valid_open_ended_accepted(self):
        payload = OpenEndedGenerationPayload.model_validate(self._valid_payload())
        assert payload.difficulty.value == "hard"
        assert len(payload.rubric) == 3

    def test_rubric_weights_not_summing_to_one_rejected(self):
        data = self._valid_payload()
        data["rubric"] = [
            {"criterion": "Criterion A", "weight": 0.4},
            {"criterion": "Criterion B", "weight": 0.4},
            # sum = 0.8 ≠ 1.0
        ]
        with pytest.raises(ValidationError, match="sum to 1.0"):
            OpenEndedGenerationPayload.model_validate(data)

    def test_rubric_weights_within_tolerance(self):
        """Weights summing to 0.99 (within 0.05 tolerance) are accepted."""
        data = self._valid_payload()
        data["rubric"] = [
            {"criterion": "Criterion A", "weight": 0.34},
            {"criterion": "Criterion B", "weight": 0.33},
            {"criterion": "Criterion C", "weight": 0.33},
        ]
        payload = OpenEndedGenerationPayload.model_validate(data)
        assert len(payload.rubric) == 3

    def test_empty_rubric_rejected(self):
        data = self._valid_payload()
        data["rubric"] = []
        with pytest.raises(ValidationError):
            OpenEndedGenerationPayload.model_validate(data)

    def test_reference_answer_too_short_rejected(self):
        data = self._valid_payload()
        data["reference_answer"] = "Short."
        with pytest.raises(ValidationError):
            OpenEndedGenerationPayload.model_validate(data)

    def test_missing_source_chunk_ids_rejected(self):
        data = self._valid_payload()
        data["source_chunk_ids"] = []
        with pytest.raises(ValidationError):
            OpenEndedGenerationPayload.model_validate(data)

    def test_criterion_weight_out_of_range_rejected(self):
        data = self._valid_payload()
        data["rubric"] = [
            {"criterion": "Criterion A", "weight": 1.5},  # >1.0
        ]
        with pytest.raises(ValidationError):
            OpenEndedGenerationPayload.model_validate(data)

    def test_option_id_pattern_enforcement(self):
        """MCQ option id must match [A-D] pattern."""
        with pytest.raises(ValidationError):
            MCQOption(id="E", text="Invalid option")
        with pytest.raises(ValidationError):
            MCQOption(id="a", text="Lowercase not allowed")
        option = MCQOption(id="B", text="Valid option")
        assert option.id == "B"
