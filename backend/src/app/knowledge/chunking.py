"""Deterministic RAG chunking strategy (Phase 3).

Key invariants:
- Zero-loss citation traceability: chunks always retain page_id and page_number.
- Structure-aware paragraph/block grouping.
- Deterministic ordering with sequential chunk_index.
- Token count and character count estimation.
- Configurable target_tokens (~500) and overlap_ratio (~0.15).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.platform.ids import uuid7


@dataclass(frozen=True)
class PageInput:
    page_id: uuid.UUID
    page_number: int
    text: str


@dataclass(frozen=True)
class ChunkDraft:
    id: uuid.UUID
    page_id: uuid.UUID
    page_start: int
    page_end: int
    chunk_index: int
    content: str
    token_count: int
    char_count: int


def estimate_tokens(text: str) -> int:
    """Heuristic token estimator: ~4 characters per token or whitespace words * 1.3."""
    if not text:
        return 0
    words = len(text.split())
    by_chars = max(1, len(text) // 4)
    return max(words, by_chars)


def split_into_paragraphs(text: str) -> list[str]:
    """Split text into blocks using paragraph breaks or line breaks."""
    raw_blocks = re.split(r"\n\s*\n", text)
    cleaned = [b.strip() for b in raw_blocks if b.strip()]
    if not cleaned:
        # Fall back to single newlines if no double newlines exist
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return lines
    return cleaned


def create_chunks_for_pages(
    pages: list[PageInput],
    *,
    target_tokens: int = 500,
    overlap_ratio: float = 0.15,
) -> list[ChunkDraft]:
    """Create deterministic, structure-aware chunks across pages.

    Preserves page boundaries and assigns sequential chunk_index.
    """
    target_chars = target_tokens * 4
    overlap_chars = int(target_chars * overlap_ratio)

    chunks: list[ChunkDraft] = []
    chunk_index = 0

    for page in pages:
        page_text = page.text.strip()
        if not page_text:
            continue

        paragraphs = split_into_paragraphs(page_text)
        current_block: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if current_len + para_len > target_chars and current_block:
                chunk_text = "\n\n".join(current_block)
                chunks.append(
                    ChunkDraft(
                        id=uuid7(),
                        page_id=page.page_id,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        chunk_index=chunk_index,
                        content=chunk_text,
                        token_count=estimate_tokens(chunk_text),
                        char_count=len(chunk_text),
                    )
                )
                chunk_index += 1

                # Overlap: keep last paragraph if it fits in overlap_chars
                if current_block and len(current_block[-1]) <= overlap_chars:
                    current_block = [current_block[-1], para]
                    current_len = len(current_block[0]) + para_len + 2
                else:
                    current_block = [para]
                    current_len = para_len
            else:
                current_block.append(para)
                current_len += para_len + 2

        if current_block:
            chunk_text = "\n\n".join(current_block)
            chunks.append(
                ChunkDraft(
                    id=uuid7(),
                    page_id=page.page_id,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    chunk_index=chunk_index,
                    content=chunk_text,
                    token_count=estimate_tokens(chunk_text),
                    char_count=len(chunk_text),
                )
            )
            chunk_index += 1

    return chunks
