# AI Tutor Subsystem Architecture (Phase 4)

## 1. Responsibilities

The `app.tutor` module manages:
1. **Conversation Lifecycle:** Project-scoped sessions, turn history, and pagination.
2. **Context Composition:** Budgeting context across system rules, retrieved evidence chunks, and prior conversation turns.
3. **Structured Grounded Generation:** Interfacing exclusively with `AIGateway` using validated Pydantic schemas (`TutorGenerationPayload`).
4. **Citation Validation:** Verifying all model-claimed citations against actual retrieved evidence bounds.
5. **SSE Streaming:** Emitting typed Server-Sent Events (`message_start`, `retrieval_complete`, `token`, `citation`, `insufficient`, `message_end`).
6. **Atomic Persistence:** Persisting assistant messages, citations, and conversation timestamps in a single database transaction.

---

## 2. Conversation Data Model

```text
projects (id)
  └── conversations (id, project_id, owner_id, title, timestamps)
        └── messages (id, conversation_id, project_id, owner_id, role, content, answer_status, idempotency_key)
              └── message_citations (id, message_id, chunk_id, document_id, material_id, page_number, quote)
```
