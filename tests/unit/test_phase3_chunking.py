"""Unit tests for Phase 3 RAG chunking algorithm."""

from app.knowledge import chunking
from app.platform.ids import uuid7


def test_estimate_tokens():
    assert chunking.estimate_tokens("") == 0
    assert chunking.estimate_tokens("word") >= 1
    # 100 characters should estimate ~25 tokens
    text = "a" * 100
    assert chunking.estimate_tokens(text) == 25


def test_split_into_paragraphs():
    raw = "Paragraph 1.\n\nParagraph 2 with more words.\n\n\nParagraph 3."
    blocks = chunking.split_into_paragraphs(raw)
    assert len(blocks) == 3
    assert blocks[0] == "Paragraph 1."
    assert blocks[1] == "Paragraph 2 with more words."
    assert blocks[2] == "Paragraph 3."


def test_create_chunks_preserves_page_lineage():
    p1_id = uuid7()
    p2_id = uuid7()
    pages = [
        chunking.PageInput(
            page_id=p1_id,
            page_number=1,
            text="First page introductory paragraph.\n\nSecond paragraph on page 1.",
        ),
        chunking.PageInput(
            page_id=p2_id,
            page_number=2,
            text="Page 2 technical explanation of the loss function.",
        ),
    ]

    chunks = chunking.create_chunks_for_pages(pages, target_tokens=100, overlap_ratio=0.15)
    assert len(chunks) >= 2

    # Verify sequential chunk_index
    for idx, chunk in enumerate(chunks):
        assert chunk.chunk_index == idx
        assert chunk.token_count > 0
        assert chunk.char_count == len(chunk.content)

    # First chunk is on page 1
    assert chunks[0].page_id == p1_id
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 1

    # Last chunk is on page 2
    assert chunks[-1].page_id == p2_id
    assert chunks[-1].page_start == 2
    assert chunks[-1].page_end == 2


def test_chunking_handles_empty_or_whitespace_pages():
    pages = [
        chunking.PageInput(page_id=uuid7(), page_number=1, text="   \n\n  "),
        chunking.PageInput(page_id=uuid7(), page_number=2, text="Valid content on page 2."),
    ]
    chunks = chunking.create_chunks_for_pages(pages, target_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].page_start == 2
    assert "Valid content" in chunks[0].content
