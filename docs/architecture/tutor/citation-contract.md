# Citation Contract & Validation (Phase 4)

## 1. Citation Invariants

1. **Existence Invariant:** Every citation must refer to a `chunk_id` that was present in the retrieved evidence set for that specific turn.
2. **Page Range Invariant:** The cited `page_number` must fall within `[page_start, page_end]` of the cited chunk.
3. **Project Invariant:** The citation must resolve to the active `project_id`.

---

## 2. Validation Algorithm

```python
for citation in model_output.citations:
    ref = evidence_map.get(citation.chunk_id)
    if not ref:
        strip_citation(citation, reason="non_retrieved_chunk")
        continue
    if citation.page < ref.page_start or citation.page > ref.page_end:
        clamp_citation(citation, target=ref.page_start)
    add_valid_citation(citation)

if model_output.grounded and len(valid_citations) == 0:
    downgrade_to_refusal(answer_status="insufficient_evidence")
```
