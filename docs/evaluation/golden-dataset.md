# Golden Evaluation Dataset — Schema and Examples

**Status:** Schema definition for review. **No evaluation results exist.** The examples below are **clearly marked synthetic illustrations of the schema** — they are not measured results, not real materials, and not evidence of system behavior. The real dataset is authored during the build (assumption A-21) from real sample documents, with human labels.

**Dataset purpose (FR-83/FR-84):** a stable, versioned fixture set that (a) gates regressions in CI and (b) calibrates the `TBD` thresholds in `evaluation-strategy.md`.

---

## 1. Dataset organization

```text
evaluation/
├── corpus/                          # sample documents ingested to form test projects
│   ├── manifest.json                # document inventory: ids, titles, page maps, topics covered/absent
│   └── docs/                        # the sample PDFs (real, licensed material — never fabricated "results")
├── datasets/
│   ├── tutor_cases.jsonl
│   ├── retrieval_cases.jsonl
│   ├── assessment_cases.jsonl
│   ├── recommendation_cases.jsonl
│   └── mastery_trajectories.jsonl   # deterministic math fixtures (hand-computed)
├── labels/                          # human label records + labeller ids (provenance of ground truth)
└── baselines/                       # stored metric baselines (populated only by real runs)
```

**Versioning rule:** dataset version (`dataset_version` in every record) bumps on any content change; CI pins the version under test; changing a case invalidates its stored baseline contribution (re-run required). Corpus documents carry checksums so retrieval labels remain verifiable against the exact ingested text.

**Labelling provenance:** every `expected_*` field traces to a human label record (`labels/`) with labeller id and date; model-judges are validated against these labels before gating (evaluation-strategy §1).

---

## 2. Tutor case schema (`tutor_cases.jsonl`)

```json
{
  "case_id": "string (stable id, e.g. tutor-0001)",
  "dataset_version": "string",
  "project_ref": {
    "corpus_project": "string (which corpus project to ingest for this case)",
    "document_ids": ["string"],
    "relevant_document_ids": ["string"],
    "relevant_pages": [{"document_id": "string", "pages": [14, 15]}]
  },
  "conversation_seed": [
    {"role": "user | assistant", "content": "string"}
  ],
  "question": "string",
  "expected_evidence": [
    {
      "document_id": "string",
      "pages": [14],
      "chunk_hint": "string (section path or quoted anchor text for labellers)",
      "must_cite": true
    }
  ],
  "expected_answer_characteristics": {
    "should_answer": true,
    "should_reference_prior_turn": false,
    "should_include_example": false,
    "should_simplify": false,
    "key_points_that_must_appear": ["short label per point (checked by judge, not string-match)"],
    "content_that_must_not_appear": ["string (e.g. concepts absent from corpus)"]
  },
  "expected_citation_characteristics": {
    "citations_required": true,
    "min_citations": 1,
    "every_citation_must_be_in_expected_evidence": true,
    "page_attribution_required": true
  },
  "refusal_expected": false,
  "refusal_reason_code_if_refused": null,
  "general_knowledge_optin_case": false,
  "difficulty_band": "easy | medium | hard",
  "labels": [{"labeller_id": "string", "date": "date", "notes": "string?"}]
}
```

**Unanswerable variant:** same schema with `refusal_expected: true`, `refusal_reason_code_if_refused` ∈ {`no_supporting_evidence`, `topic_absent`, `tangential_only`}, `expected_evidence: []`, `should_answer: false`, and optional `general_knowledge_optin_case: true` (turn 2 of the case opts in and asserts the general-knowledge answer is visibly labelled, not mixed with citations).

### 2.1 SYNTHETIC EXAMPLE — answerable case (schema illustration only)

```json
{
  "case_id": "tutor-0001",
  "dataset_version": "0.1-synthetic",
  "project_ref": {
    "corpus_project": "ml-fundamentals",
    "document_ids": ["doc-ml-notes"],
    "relevant_document_ids": ["doc-ml-notes"],
    "relevant_pages": [{"document_id": "doc-ml-notes", "pages": [14, 15]}]
  },
  "conversation_seed": [],
  "question": "How does gradient descent choose its step size?",
  "expected_evidence": [
    {"document_id": "doc-ml-notes", "pages": [14], "chunk_hint": "§3.2 Learning rate", "must_cite": true},
    {"document_id": "doc-ml-notes", "pages": [15], "chunk_hint": "§3.3 Adaptive step sizes", "must_cite": false}
  ],
  "expected_answer_characteristics": {
    "should_answer": true,
    "should_reference_prior_turn": false,
    "should_include_example": false,
    "should_simplify": false,
    "key_points_that_must_appear": ["fixed learning rate baseline", "adaptive methods adjust per-parameter"],
    "content_that_must_not_appear": ["Nesterov-style momentum variants (absent from corpus)"]
  },
  "expected_citation_characteristics": {
    "citations_required": true,
    "min_citations": 1,
    "every_citation_must_be_in_expected_evidence": true,
    "page_attribution_required": true
  },
  "refusal_expected": false,
  "refusal_reason_code_if_refused": null,
  "general_knowledge_optin_case": false,
  "difficulty_band": "medium",
  "labels": [{"labeller_id": "TBD-assigned-at-authoring", "date": null, "notes": "synthetic schema example"}]
}
```

### 2.2 SYNTHETIC EXAMPLE — unanswerable / refusal case (schema illustration only)

```json
{
  "case_id": "tutor-0002",
  "dataset_version": "0.1-synthetic",
  "project_ref": {
    "corpus_project": "ml-fundamentals",
    "document_ids": ["doc-ml-notes"],
    "relevant_document_ids": [],
    "relevant_pages": []
  },
  "conversation_seed": [],
  "question": "What did the 2026 NeurIPS benchmark say about optimizer convergence?",
  "expected_evidence": [],
  "expected_answer_characteristics": {
    "should_answer": false,
    "should_reference_prior_turn": false,
    "should_include_example": false,
    "should_simplify": false,
    "key_points_that_must_appear": [],
    "content_that_must_not_appear": ["any substantive claim about the 2026 benchmark"]
  },
  "expected_citation_characteristics": {
    "citations_required": false,
    "min_citations": 0,
    "every_citation_must_be_in_expected_evidence": true,
    "page_attribution_required": false
  },
  "refusal_expected": true,
  "refusal_reason_code_if_refused": "topic_absent",
  "general_knowledge_optin_case": false,
  "difficulty_band": "easy",
  "labels": [{"labeller_id": "TBD-assigned-at-authoring", "date": null, "notes": "synthetic schema example"}]
}
```

---

## 3. Retrieval case schema (`retrieval_cases.jsonl`)

```json
{
  "case_id": "string",
  "dataset_version": "string",
  "query": "string (user-phrased; paraphrase and exact-term variants included deliberately)",
  "query_type": "paraphrase | exact_term | formula_or_acronym | conversational_followup",
  "project_ref": {"corpus_project": "string", "document_ids": ["string"]},
  "relevant_chunks": [
    {"document_id": "string", "page_start": 14, "page_end": 14,
     "chunk_hint": "anchor text", "relevance_grade": 3}
  ],
  "expected_ranking": {
    "primary_chunk_must_rank_within_k": 6,
    "ordering_constraint": "string? (e.g. 'grade-3 chunk above grade-1 chunks')"
  },
  "expected_sufficiency": "sufficient | insufficient",
  "labels": [{"labeller_id": "string", "date": "date"}]
}
```

`relevance_grade`: 3 = directly answers, 2 = strongly supportive, 1 = background-only. Grades are human labels (evaluation-strategy §2.2).

### 3.1 SYNTHETIC EXAMPLE (schema illustration only)

```json
{
  "case_id": "retr-0001",
  "dataset_version": "0.1-synthetic",
  "query": "why does my model stop improving even though it's still learning?",
  "query_type": "paraphrase",
  "project_ref": {"corpus_project": "ml-fundamentals", "document_ids": ["doc-ml-notes"]},
  "relevant_chunks": [
    {"document_id": "doc-ml-notes", "page_start": 21, "page_end": 21, "chunk_hint": "§5.1 Overfitting", "relevance_grade": 3},
    {"document_id": "doc-ml-notes", "page_start": 22, "page_end": 22, "chunk_hint": "§5.2 Regularization intro", "relevance_grade": 1}
  ],
  "expected_ranking": {"primary_chunk_must_rank_within_k": 6, "ordering_constraint": "grade-3 above grade-1"},
  "expected_sufficiency": "sufficient",
  "labels": [{"labeller_id": "TBD-assigned-at-authoring", "date": null}]
}
```

---

## 4. Assessment case schema (`assessment_cases.jsonl`)

```json
{
  "case_id": "string",
  "dataset_version": "string",
  "question": {
    "text": "string",
    "type": "mcq | open_ended",
    "options": ["string"]?,
    "correct_option_index": "int?",
    "rubric": {
      "criteria": [{"name": "string", "points": "number", "description": "string"}],
      "expected_concepts": ["concept labels"],
      "common_misconceptions": ["string"]
    }?,
    "source_chunk_refs": [{"document_id": "string", "pages": ["int"]}]
  },
  "student_answer": {
    "selected_option_index": "int?",
    "response_text": "string?"
  },
  "expected_grading_dimensions": {
    "score_range": [0.0, 1.0],
    "expected_score_band": "human-labelled band, e.g. [0.6, 0.8]",
    "concepts_covered_expected": ["labels"],
    "concepts_missing_expected": ["labels"],
    "is_correct_expected": "bool?"
  },
  "expected_feedback_characteristics": {
    "must_reference_rubric_criteria": true,
    "must_explain_not_just_score": true,
    "must_not_reveal_correct_option_on_mcq_first_pass": true,
    "tone": "constructive, specific"
  },
  "grading_expected_flag": "deterministic | ai | pending_review",
  "labels": [{"labeller_id": "string", "date": "date", "second_labeller_id": "string?"}]
}
```

### 4.1 SYNTHETIC EXAMPLE (schema illustration only)

```json
{
  "case_id": "asmt-0001",
  "dataset_version": "0.1-synthetic",
  "question": {
    "text": "Explain, in your own words, why a high learning rate can prevent convergence.",
    "type": "open_ended",
    "rubric": {
      "criteria": [
        {"name": "oscillation_explanation", "points": 0.5, "description": "overshooting the minimum"},
        {"name": "divergence_note", "points": 0.3, "description": "loss can increase/diverge"},
        {"name": "correct_language", "points": 0.2, "description": "uses step-size/gradient terms correctly"}
      ],
      "expected_concepts": ["learning rate", "gradient descent"],
      "common_misconceptions": ["higher learning rate always converges faster"]
    },
    "source_chunk_refs": [{"document_id": "doc-ml-notes", "pages": [14]}]
  },
  "student_answer": {
    "response_text": "The steps are so big that you jump over the valley and the loss can go up instead of down."
  },
  "expected_grading_dimensions": {
    "score_range": [0.0, 1.0],
    "expected_score_band": [0.6, 0.85],
    "concepts_covered_expected": ["learning rate"],
    "concepts_missing_expected": ["divergence terminology"],
    "is_correct_expected": null
  },
  "expected_feedback_characteristics": {
    "must_reference_rubric_criteria": true,
    "must_explain_not_just_score": true,
    "must_not_reveal_correct_option_on_mcq_first_pass": true,
    "tone": "constructive, specific"
  },
  "grading_expected_flag": "ai",
  "labels": [{"labeller_id": "TBD-assigned-at-authoring", "date": null}]
}
```

---

## 5. Recommendation case schema (`recommendation_cases.jsonl`)

```json
{
  "case_id": "string",
  "dataset_version": "string",
  "learning_state": {
    "corpus_project": "string",
    "goal": "string",
    "mastery_snapshot": [{"concept_label": "string", "mastery": 0.0, "confidence": 0.0}],
    "weak_concepts": ["labels"],
    "recent_mistakes": [{"concept_label": "string", "count": "int", "window_days": "int"}],
    "available_materials": [{"document_id": "string", "topic_labels": ["string"]}],
    "existing_active_recommendations": [{"kind": "string", "target_concept_labels": ["string"]}]
  },
  "expected_recommendation_characteristics": {
    "acceptable_kinds": ["review_material", "take_quiz", "tutor_session", "revisit_concept", "new_material"],
    "must_target_weak_concepts": true,
    "must_reference_goal": false,
    "must_be_actionable": true,
    "must_not_duplicate_existing": true
  },
  "labels": [{"labeller_id": "string", "date": "date"}]
}
```

### 5.1 SYNTHETIC EXAMPLE (schema illustration only)

```json
{
  "case_id": "rec-0001",
  "dataset_version": "0.1-synthetic",
  "learning_state": {
    "corpus_project": "ml-fundamentals",
    "goal": "Understand core optimization methods well enough to apply them",
    "mastery_snapshot": [
      {"concept_label": "gradient descent", "mastery": 0.35, "confidence": 0.7},
      {"concept_label": "overfitting", "mastery": 0.8, "confidence": 0.6}
    ],
    "weak_concepts": ["gradient descent"],
    "recent_mistakes": [{"concept_label": "gradient descent", "count": 3, "window_days": 7}],
    "available_materials": [{"document_id": "doc-ml-notes", "topic_labels": ["gradient descent", "overfitting"]}],
    "existing_active_recommendations": []
  },
  "expected_recommendation_characteristics": {
    "acceptable_kinds": ["revisit_concept", "take_quiz", "tutor_session"],
    "must_target_weak_concepts": true,
    "must_reference_goal": false,
    "must_be_actionable": true,
    "must_not_duplicate_existing": true
  },
  "labels": [{"labeller_id": "TBD-assigned-at-authoring", "date": null}]
}
```

---

## 6. Mastery trajectory fixtures (`mastery_trajectories.jsonl`)

Deterministic math fixtures: input evidence sequences with hand-computed expected trajectories (evaluated exactly, evaluation-strategy §2.8). Schema:

```json
{
  "case_id": "string",
  "description": "string (e.g. 'correct answers with decay gap')",
  "initial_state": {"mastery": 0.3, "confidence": 0.1, "last_evidence_at": "date?"},
  "evidence_sequence": [
    {"source": "quiz_answer", "source_id": "synthetic", "is_correct": true, "evidence_strength": 0.8, "difficulty": 0.5, "days_after_previous": 0}
  ],
  "expected": {"final_mastery": 0.0, "final_confidence": 0.0, "tolerance": "TBD — set when fixtures are authored"},
  "invariants": ["order_independence", "range_0_1", "no_nan"],
  "label_author": "reviewer (math is hand-computed, then reviewed)"
}
```

Covered fixture families (minimum): monotone-correct sequence; mixed correct/incorrect; long-gap decay; contradictory evidence; single-evidence cold start; empty sequence; duplicate evidence id (idempotency).

---

## 7. Authoring plan (real dataset, not results)

1. **Select 3–5 real, licensed sample documents** spanning: clean native text; a scanned/OCR page; a document with tables; one with figures/diagrams (covers FR-22 robustness labels).
2. **Ingest them into a dedicated evaluation project**; record the corpus manifest (ids, checksums, page maps).
3. **Author cases against the real corpus:** ~2–3 answerable tutor cases per document/topic + deliberately unanswerable + near-miss band; retrieval cases with grades; assessment cases with double-labelled gradings on disputed ones; recommendation states derived from plausible mastery snapshots; mastery fixtures hand-computed and reviewer-verified.
4. **Label with provenance** (`labels/`), two labellers where judgment-heavy.
5. **First full run → populate baselines** → calibrate the `TBD` thresholds in evaluation-strategy.md §4 → arm the remaining gates.

Case-count targets for the first calibrated dataset (order-of-magnitude, not results): tutor ≈ 30–60 (incl. ≥ 10 unanswerable + ≥ 10 near-miss), retrieval ≈ 40–80, assessment ≈ 20–40, recommendations ≈ 15–30, mastery fixtures ≈ 7+ families. These are authoring budgets, **not** performance claims.
