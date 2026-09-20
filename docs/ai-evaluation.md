# AI Evaluation Framework (Phase 11)

## Overview
The AI Study Companion enforces strict deterministic evaluation disciplines to ensure groundedness, safety, citation precision, and recommendation reproducibility.

---

## 1. Retrieval Metrics
Retrieval evaluation runs against benchmark query-evidence pairs:
- **Recall@1**: Proportion of queries where the top retrieved chunk is relevant.
- **Recall@3**: Proportion of queries where at least one relevant chunk appears in the top 3.
- **Recall@5**: Proportion of queries where at least one relevant chunk appears in the top 5.
- **Mean Reciprocal Rank (MRR)**: Average reciprocal rank of the first relevant chunk.

## 2. Tutor Groundedness & Refusal
- **Citation Precision**: $\frac{\text{Valid Citations}}{\text{Total Citations}}$ where validity requires chunk existence, project ownership match, and page accuracy.
- **Unsupported Question Refusal Rate**: Proportion of queries outside document scope that trigger honest refusal (`answer_status = "insufficient_evidence"`). Target: 100%.

## 3. Assessment & MCQ Quality
- **Single Correct Answer**: Every generated MCQ has exactly 1 correct option and 3 plausible distractors.
- **Grounding**: Question concepts and reference answers must directly map to ingested document chunks.

## 4. Recommendation Determinism
- Recommendation candidates are generated from mathematical concept states (mastery probability, growth trend, velocity, and error rates).
- Scoring is strictly deterministic within $[0.0, 1.0]$.
