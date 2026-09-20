"""Question generation — RAG-grounded, AI-Gateway-mediated, validated.

Pipeline:
    Evidence (from KnowledgeService)
        ↓
    Structured prompt → AI Gateway (assessment_question_generation)
        ↓
    Raw output
        ↓
    Pydantic validation (MCQGenerationPayload / OpenEndedGenerationPayload)
        ↓
    Project-scope validation (chunk ids belong to this project)
        ↓
    Persist (only if valid)

NEVER calls a model provider directly. NEVER bypasses the AI Gateway.
NEVER persists invalid questions.

Prompt injection defense: evidence text is wrapped inside
<retrieved_evidence>...</retrieved_evidence> so it cannot be promoted
to system instructions even if it contains adversarial content.
"""

from __future__ import annotations

import uuid

from app.ai.schemas import StructuredRequest
from app.assessment.schemas import (
    MCQGenerationPayload,
    OpenEndedGenerationPayload,
)
from app.knowledge.schemas import EvidenceSetDto
from app.platform.errors import AIInvalidOutput, ValidationError
from app.platform.logging import get_logger

logger = get_logger(__name__)

_MCQ_MAX_CHUNKS = 3  # max evidence chunks to include in generation prompt


def _build_evidence_block(evidence: EvidenceSetDto, max_chunks: int = _MCQ_MAX_CHUNKS) -> str:
    """Format retrieved evidence for the generation prompt.

    Evidence is wrapped in a named XML-like boundary to prevent prompt
    injection: even if a chunk contains 'Ignore previous instructions',
    it remains inside the data boundary and cannot become system behavior.
    """
    hits = evidence.hits[:max_chunks]
    lines = []
    for hit in hits:
        ref = hit.chunk_ref
        lines.append(
            f'<chunk id="{ref.chunk_id}" page_start="{ref.page_start}" '
            f'page_end="{ref.page_end}">\n{ref.text}\n</chunk>'
        )
    return "<retrieved_evidence>\n" + "\n".join(lines) + "\n</retrieved_evidence>"


def _validate_chunk_ids_in_scope(
    chunk_ids: list[str],
    evidence: EvidenceSetDto,
    project_id: uuid.UUID,
) -> None:
    """Reject questions whose source chunks are outside the current project scope."""
    valid_chunk_ids = {str(h.chunk_ref.chunk_id) for h in evidence.hits}
    for cid in chunk_ids:
        if cid not in valid_chunk_ids:
            raise ValidationError(
                f"Source chunk_id '{cid}' is not part of project {project_id} evidence. "
                "Generated question violates grounding contract."
            )


async def generate_mcq_question(
    *,
    evidence: EvidenceSetDto,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    difficulty: str = "medium",
    ordinal: int = 1,
) -> dict:
    """Generate one MCQ question grounded in project evidence.

    Returns a dict with all question data including the answer key.
    The caller (service) is responsible for persisting and for NEVER
    exposing correct_option in the API response.

    Raises ValidationError if generation produces invalid output.
    Raises AIInvalidOutput if the AI Gateway rejects the structured output.
    """
    from app.ai.gateway import get_gateway

    if not evidence.hits:
        raise ValidationError("Cannot generate MCQ: no evidence hits available")

    evidence_block = _build_evidence_block(evidence)
    prompt = (
        f"You are an expert question generator for an adaptive learning system.\n\n"
        f"Generate ONE {difficulty.upper()} difficulty MCQ question based ONLY on the "
        f"evidence provided below. Do NOT use general knowledge outside the evidence.\n\n"
        f"{evidence_block}\n\n"
        f"Return a JSON object with exactly this structure:\n"
        f"{{\n"
        f'  "question_type": "mcq",\n'
        f'  "difficulty": "{difficulty}",\n'
        f'  "question": "...(the question text)...",\n'
        f'  "options": [\n'
        f'    {{"id": "A", "text": "..."}},\n'
        f'    {{"id": "B", "text": "..."}},\n'
        f'    {{"id": "C", "text": "..."}},\n'
        f'    {{"id": "D", "text": "..."}}\n'
        f"  ],\n"
        f'  "correct_option": "B",\n'
        f'  "explanation": "...(why the correct option is correct based on the evidence)...",\n'
        f'  "source_chunk_ids": ["...chunk id from evidence..."]\n'
        f"}}\n\n"
        f"Requirements:\n"
        f"- Question must be answerable from the evidence only.\n"
        f"- Exactly 4 options (A, B, C, D) with unique texts.\n"
        f"- correct_option must be one of A, B, C, D.\n"
        f"- source_chunk_ids must be chunk ids from the evidence above.\n"
        f"- Do NOT expose the answer in the question text."
    )

    gateway = get_gateway()
    result = await gateway.generate_structured(
        StructuredRequest(
            feature="assessment_question_generation",
            prompt=prompt,
            output_schema_name="MCQGenerationPayload",
            schema_model=MCQGenerationPayload,
        )
    )

    if result.data is None:
        raise AIInvalidOutput("MCQ generation returned no data")

    # Validate against Pydantic schema
    try:
        payload = MCQGenerationPayload.model_validate(result.data)
    except Exception as exc:
        raise ValidationError(f"MCQ generation output failed validation: {exc}") from exc

    # Validate chunk ids are in project scope
    _validate_chunk_ids_in_scope(payload.source_chunk_ids, evidence, project_id)

    logger.info(
        "mcq_question_generated",
        extra={
            "details": {
                "project_id": str(project_id),
                "difficulty": difficulty,
                "ai_request_id": result.meta.ai_request_id,
                "ordinal": ordinal,
            }
        },
    )

    return {
        "question_type": "mcq",
        "difficulty": payload.difficulty.value,
        "question_text": payload.question,
        "correct_option": payload.correct_option,
        "reference_answer": None,
        "rubric": None,
        "explanation": payload.explanation,
        "source_chunk_ids": payload.source_chunk_ids,
        "options": [{"id": o.id, "text": o.text} for o in payload.options],
        "generation_model": result.meta.model,
        "ai_request_id": result.meta.ai_request_id,
        "ordinal": ordinal,
    }


async def generate_open_ended_question(
    *,
    evidence: EvidenceSetDto,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    difficulty: str = "medium",
    ordinal: int = 1,
) -> dict:
    """Generate one open-ended question grounded in project evidence.

    Returns a dict with all question data including reference_answer and rubric.
    The caller must NEVER expose reference_answer or rubric in the API response.

    Raises ValidationError if generation produces invalid output.
    """
    from app.ai.gateway import get_gateway

    if not evidence.hits:
        raise ValidationError("Cannot generate open-ended question: no evidence hits available")

    evidence_block = _build_evidence_block(evidence)
    prompt = (
        f"You are an expert question generator for an adaptive learning system.\n\n"
        f"Generate ONE {difficulty.upper()} difficulty open-ended question based ONLY on "
        f"the evidence provided below. Do NOT use general knowledge outside the evidence.\n\n"
        f"{evidence_block}\n\n"
        f"Return a JSON object with exactly this structure:\n"
        f"{{\n"
        f'  "question_type": "open_ended",\n'
        f'  "difficulty": "{difficulty}",\n'
        f'  "question": "...(the question text)...",\n'
        f'  "reference_answer": "...(the ideal complete answer based on evidence)...",\n'
        f'  "rubric": [\n'
        f'    {{"criterion": "...", "weight": 0.4}},\n'
        f'    {{"criterion": "...", "weight": 0.3}},\n'
        f'    {{"criterion": "...", "weight": 0.3}}\n'
        f"  ],\n"
        f'  "source_chunk_ids": ["...chunk id from evidence..."]\n'
        f"}}\n\n"
        f"Requirements:\n"
        f"- Question must be answerable from the evidence only.\n"
        f"- rubric criterion weights must sum to 1.0.\n"
        f"- source_chunk_ids must be chunk ids from the evidence above.\n"
        f"- reference_answer must be based only on the evidence, not world knowledge."
    )

    gateway = get_gateway()
    result = await gateway.generate_structured(
        StructuredRequest(
            feature="assessment_question_generation",
            prompt=prompt,
            output_schema_name="OpenEndedGenerationPayload",
            schema_model=OpenEndedGenerationPayload,
        )
    )

    if result.data is None:
        raise AIInvalidOutput("Open-ended generation returned no data")

    try:
        payload = OpenEndedGenerationPayload.model_validate(result.data)
    except Exception as exc:
        raise ValidationError(f"Open-ended generation output failed validation: {exc}") from exc

    _validate_chunk_ids_in_scope(payload.source_chunk_ids, evidence, project_id)

    logger.info(
        "open_ended_question_generated",
        extra={
            "details": {
                "project_id": str(project_id),
                "difficulty": difficulty,
                "ai_request_id": result.meta.ai_request_id,
                "ordinal": ordinal,
            }
        },
    )

    return {
        "question_type": "open_ended",
        "difficulty": payload.difficulty.value,
        "question_text": payload.question,
        "correct_option": None,
        "reference_answer": payload.reference_answer,
        "rubric": [{"criterion": c.criterion, "weight": c.weight} for c in payload.rubric],
        "source_chunk_ids": payload.source_chunk_ids,
        "options": None,
        "generation_model": result.meta.model,
        "ai_request_id": result.meta.ai_request_id,
        "ordinal": ordinal,
    }
