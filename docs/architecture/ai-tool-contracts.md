# AI Tool Contracts — Application Capability Layer

**Status:** Engineering contract for review.
**Purpose:** Define the complete, allow-listed capability catalogue available to AI. The model never receives a database connection, internal service objects, raw SQL, network access, filesystem access, or generic execution tools. Every capability below maps one-to-one to a PRD §8 interaction; there are **no other tools**. Adding a tool is a reviewed contract change, not a code convenience.

**Hard boundary rules (from project-principles.md, enforced by the Tools module):**

1. **Scope is injected, never argued.** `user_id` and `project_id` come from the server-side `ProjectScope`. Any tenant identifier appearing in tool arguments is rejected **before schema validation** (`scope_injection_violation`), audited, and treated as a security signal — not a validation error to be retried.
2. **Calls are honoured only from the model's tool-call channel.** Retrieved material content, tool results, and user messages can never originate a tool call; they are data.
3. **Per-feature allow-lists.** Each calling feature declares which tools it may use (table §3). A tool invoked from a non-allow-listed feature is denied.
4. **Bounded loop.** The calling orchestrator (Tutor) enforces max steps (default 4) and a wall-clock budget; the executor enforces per-invocation result caps.
5. **Read before write.** Write-capable tools require a model-supplied `justification` string, persisted with the audit record.
6. **Everything is audited** — authorized or denied — with arguments, outcome, and latency.
7. **Errors are data.** Failures return structured error results to the model (one repair retry allowed by the orchestrator); they are never thrown into the model channel.

**Common invocation envelope (executor-internal):**

```text
ToolCall    = { ai_request_id, feature, name, arguments: JSON, justification?: str }
ToolResult  = { invocation_id, status: success | validation_error | denied | execution_error,
                data?: JSON (size-capped, redacted), error?: { code, message } }
```

---

## 1. Tool catalogue

| # | Tool | Category | Write? | Allowed callers (§3) |
|---|---|---|---|---|
| 1 | `search_project_materials` | Search / evidence | No | tutor, quiz_generation |
| 2 | `retrieve_project_evidence` | Search / evidence | No | tutor |
| 3 | `get_project_progress` | Learner state | No | tutor, recommendation_engine |
| 4 | `get_mastery_summary` | Learner state | No | tutor, quiz_generation, recommendation_engine |
| 5 | `get_weak_concepts` | Learner state | No | tutor, quiz_generation, recommendation_engine |
| 6 | `get_learning_context` | Learner state | No | tutor |
| 7 | `get_assessment_history` | Learner state | No | tutor, quiz_generation, recommendation_engine |
| 8 | `generate_quiz` | Action / write | Yes | tutor (practice intent), quiz_generation |
| 9 | `record_learning_event` | Action / write | Yes | tutor, learning_context_extractor |
| 10 | `update_learning_context` | Action / write | Yes | tutor, learning_context_extractor |
| 11 | `record_recommendation` | Action / write | Yes | recommendation_engine |

`execute_sql`, `database_query`, `arbitrary_http_request`, `filesystem_access`, `shell_execution`, and any "run code / generic fetch" capability are **prohibited by design** and cannot be registered — the registry validates names against this catalogue.

---

## 2. Tool specifications

### 2.1 `search_project_materials`

| Aspect | Specification |
|---|---|
| **Purpose** | Keyword/semantic search over the project's ingested material (find where something is discussed) |
| **Input JSON schema** | `{ "type": "object", "required": ["query"], "properties": { "query": {"type": "string", "minLength": 1, "maxLength": 500}, "material_id": {"type": "string", "format": "uuid"}, "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5} }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["hits"], "properties": { "hits": { "type": "array", "items": { "type": "object", "required": ["material_title", "page_start", "page_end", "excerpt"], "properties": { "chunk_id": {"type": "string"}, "material_title": {"type": "string"}, "page_start": {"type": "integer"}, "page_end": {"type": "integer"}, "section_path": {"type": "string"}, "excerpt": {"type": "string", "maxLength": 600} } } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes — search restricted to scope's project, filter inside the query |
| **Validation rules** | Query non-empty; `k ≤ 10`; `material_id` (if present) must belong to scope; excerpts size-capped server-side |
| **Side effects** | None (read) |
| **Idempotency** | Naturally read-only; identical query may hit retrieval cache |
| **Audit** | Full record: arguments, hit count, latency |
| **Failure behavior** | Empty corpus → success with `hits: []` (model told materials may not cover it); retrieval dependency failure → `execution_error` with retryable flag |

### 2.2 `retrieve_project_evidence`

| Aspect | Specification |
|---|---|
| **Purpose** | Full evidence retrieval for grounding a claim: hybrid search + fusion + rerank + **sufficiency decision** (the Tutor's grounding primitive) |
| **Input JSON schema** | `{ "type": "object", "required": ["query"], "properties": { "query": {"type": "string", "minLength": 1, "maxLength": 1000}, "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 6} }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["sufficiency", "evidence"], "properties": { "sufficiency": { "type": "object", "required": ["sufficient", "reason_code"], "properties": { "sufficient": {"type": "boolean"}, "reason_code": {"type": "string"}, "top_score": {"type": "number"} } }, "evidence": { "type": "array", "items": { "type": "object", "required": ["evidence_id", "material_title", "page_start", "page_end", "excerpt"], "properties": { "evidence_id": {"type": "integer", "minimum": 1}, "chunk_id": {"type": "string"}, "material_title": {"type": "string"}, "page_start": {"type": "integer"}, "page_end": {"type": "integer"}, "excerpt": {"type": "string", "maxLength": 800} } } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes — in-query tenant filter; post-retrieval scope assertion |
| **Validation rules** | Query non-empty; `k ≤ 10`; evidence blocks are returned as **numbered DATA blocks** — the framing labels them reference data, never instructions |
| **Side effects** | None; retrieval_meta recorded on the enclosing AI request |
| **Idempotency** | Read-only |
| **Audit** | Full record incl. sufficiency decision |
| **Failure behavior** | Insufficiency is **not** an error — `sufficient: false` with `reason_code` is a successful, structured result the orchestrator routes to the refusal path |

### 2.3 `get_project_progress`

| Aspect | Specification |
|---|---|
| **Purpose** | Overall project learning progress (read model for "how am I doing" questions without retrieval) |
| **Input JSON schema** | `{ "type": "object", "properties": {}, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["progress"], "properties": { "progress": { "type": "object", "required": ["materials_ready", "concepts_tracked", "overall_mastery"], "properties": { "materials_ready": {"type": "integer"}, "materials_total": {"type": "integer"}, "concepts_tracked": {"type": "integer"}, "overall_mastery": {"type": ["number", "null"], "minimum": 0, "maximum": 1}, "quizzes_completed": {"type": "integer"}, "last_activity_at": {"type": ["string", "null"], "format": "date-time"} } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes |
| **Validation rules** | No arguments permitted (scope does the work) |
| **Side effects** | None |
| **Idempotency** | Read-only; may serve from dashboard rollup cache |
| **Audit** | Record (arguments empty, latency) |
| **Failure behavior** | Cold project → zeroed/null fields (valid empty state) |

### 2.4 `get_mastery_summary`

| Aspect | Specification |
|---|---|
| **Purpose** | Per-concept mastery estimates (with confidence) for the project, optionally restricted to concepts |
| **Input JSON schema** | `{ "type": "object", "properties": { "concept_ids": { "type": "array", "items": {"type": "string", "format": "uuid"}, "maxItems": 20 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["concepts"], "properties": { "concepts": { "type": "array", "items": { "type": "object", "required": ["concept_id", "concept_name", "mastery", "confidence"], "properties": { "concept_id": {"type": "string"}, "concept_name": {"type": "string"}, "mastery": {"type": "number", "minimum": 0, "maximum": 1}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "evidence_count": {"type": "integer"}, "last_evidence_at": {"type": ["string", "null"], "format": "date-time"} } } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes — requested concept ids are validated to belong to the scope |
| **Validation rules** | ≤ 20 concepts per call; foreign concept ids → scope violation |
| **Side effects** | None |
| **Idempotency** | Read-only |
| **Audit** | Record |
| **Failure behavior** | No mastery data yet → empty array (valid) |

### 2.5 `get_weak_concepts`

| Aspect | Specification |
|---|---|
| **Purpose** | Deterministic weakness ranking (low mastery, low confidence, recent mistakes) |
| **Input JSON schema** | `{ "type": "object", "properties": { "limit": { "type": "integer", "minimum": 1, "maximum": 10, "default": 5 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["weak_concepts"], "properties": { "weak_concepts": { "type": "array", "items": { "type": "object", "required": ["concept_id", "concept_name", "mastery", "confidence"], "properties": { "concept_id": {"type": "string"}, "concept_name": {"type": "string"}, "mastery": {"type": "number"}, "confidence": {"type": "number"}, "reason_code": {"type": "string", "enum": ["low_mastery", "low_evidence", "recent_mistakes", "decaying"]}, "recent_mistake_count": {"type": "integer"} } } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes |
| **Validation rules** | `limit ≤ 10` |
| **Side effects** | None |
| **Idempotency** | Read-only |
| **Audit** | Record |
| **Failure behavior** | Empty state → empty array |

### 2.6 `get_learning_context`

| Aspect | Specification |
|---|---|
| **Purpose** | Read the durable learning-context items (goals, preferences, weaknesses, recurring notes) relevant to the current turn |
| **Input JSON schema** | `{ "type": "object", "properties": { "kinds": { "type": "array", "items": { "type": "string", "enum": ["goal", "preference", "strength", "weakness", "misconception", "history", "tutor_note"] } }, "limit": { "type": "integer", "minimum": 1, "maximum": 15, "default": 10 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["items"], "properties": { "items": { "type": "array", "items": { "type": "object", "required": ["item_id", "kind", "content"], "properties": { "item_id": {"type": "string"}, "kind": {"type": "string"}, "content": {"type": "string", "maxLength": 500}, "concept_id": {"type": ["string", "null"]}, "salience": {"type": "number"}, "last_reinforced_at": {"type": "string", "format": "date-time"} } } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes |
| **Validation rules** | Kinds constrained to enum; content length-capped server-side |
| **Side effects** | None |
| **Idempotency** | Read-only |
| **Audit** | Record |
| **Failure behavior** | Empty context → empty array |

### 2.7 `get_assessment_history`

| Aspect | Specification |
|---|---|
| **Purpose** | Recent quiz performance (per answer/concept) for grounded follow-up discussion |
| **Input JSON schema** | `{ "type": "object", "properties": { "concept_id": { "type": "string", "format": "uuid" }, "limit": { "type": "integer", "minimum": 1, "maximum": 20, "default": 10 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["entries"], "properties": { "entries": { "type": "array", "items": { "type": "object", "required": ["quiz_id", "concept_id?", "question_type", "is_correct", "answered_at"], "properties": { "quiz_id": {"type": "string"}, "concept_id": {"type": ["string", "null"]}, "question_type": {"type": "string", "enum": ["mcq", "open_ended"]}, "is_correct": {"type": ["boolean", "null"]}, "score": {"type": ["number", "null"]}, "answered_at": {"type": "string", "format": "date-time"} } } } } }` |
| **Required authorization** | Project read (owner scope) |
| **Required project scope** | Yes |
| **Validation rules** | `limit ≤ 20`; **returns correctness/scores only — never the learner's free-text responses** |
| **Side effects** | None |
| **Idempotency** | Read-only |
| **Audit** | Record |
| **Failure behavior** | No history → empty array |

### 2.8 `generate_quiz`

| Aspect | Specification |
|---|---|
| **Purpose** | Create a quiz session for the project (idempotent, dedup-keyed) — e.g. user asked the Tutor for practice |
| **Input JSON schema** | `{ "type": "object", "required": ["concept_ids", "justification"], "properties": { "concept_ids": { "type": "array", "items": {"type": "string", "format": "uuid"}, "minItems": 1, "maxItems": 5 }, "question_count": { "type": "integer", "minimum": 1, "maximum": 10, "default": 5 }, "question_types": { "type": "array", "items": {"type": "string", "enum": ["mcq", "open_ended"]}, "minItems": 1 }, "justification": { "type": "string", "minLength": 10, "maxLength": 300 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["quiz_id", "status"], "properties": { "quiz_id": {"type": "string"}, "status": {"type": "string", "enum": ["in_progress"]}, "concept_ids": {"type": "array", "items": {"type": "string"}}, "question_count": {"type": "integer"} } }` |
| **Required authorization** | Project write (owner scope) + feature allow-list (Tutor may call only on explicit practice intent; the quiz-generation flow calls it as its own orchestration) |
| **Required project scope** | Yes — concept ids validated against scope; quiz created in scope's project |
| **Validation rules** | 1–5 concepts, 1–10 questions; **write-tool: justification required** and persisted; concept ids foreign to scope → `denied` (scope violation, security signal) |
| **Side effects** | Creates quiz + `QuizCreated` + `ActivityRecorded`; questions generated lazily by the quiz flow (grounded in project chunks) |
| **Idempotency** | Dedup key derived server-side from `(scope, concept set, question params, turn context)` — duplicate invocation within the dedup window returns the existing quiz instead of creating a second one |
| **Audit** | Full record incl. justification, created quiz id |
| **Failure behavior** | `EmptyCorpus` (no ready material for concepts) → `execution_error` with actionable message to the model; rate/budget caps → `denied` with reason |

### 2.9 `record_learning_event`

| Aspect | Specification |
|---|---|
| **Purpose** | Append a learner-activity event from an AI-driven flow (enum-constrained — the model cannot invent event types) |
| **Input JSON schema** | `{ "type": "object", "required": ["activity_type", "justification"], "properties": { "activity_type": { "type": "string", "enum": ["tutor_concept_discussed", "tutor_practice_requested", "concept_revisited"] }, "concept_id": { "type": ["string", "null"], "format": "uuid" }, "summary": { "type": ["string", "null"], "maxLength": 200 }, "justification": { "type": "string", "minLength": 10, "maxLength": 300 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["recorded"], "properties": { "recorded": {"type": "boolean"} } }` |
| **Required authorization** | Project write (owner scope) + feature allow-list |
| **Required project scope** | Yes |
| **Validation rules** | `activity_type` enum-locked; concept id validated to scope; summary length-capped and **labelled as model-authored content**, stored as such |
| **Side effects** | Appends an activity event (`ActivityRecorded`) |
| **Idempotency** | Dedup key `(scope, activity_type, concept_id, ai_request_id)` — a retried model step does not duplicate the event |
| **Audit** | Full record incl. justification |
| **Failure behavior** | Invalid enum → `validation_error` (model may retry once); write failure → `execution_error` |

### 2.10 `update_learning_context`

| Aspect | Specification |
|---|---|
| **Purpose** | Persist a durable learner fact surfaced in conversation (goal, misconception, preference) — the structured store behind FR-63 |
| **Input JSON schema** | `{ "type": "object", "required": ["kind", "content", "justification"], "properties": { "kind": { "type": "string", "enum": ["goal", "preference", "strength", "weakness", "misconception", "history", "tutor_note"] }, "content": { "type": "string", "minLength": 3, "maxLength": 500 }, "concept_id": { "type": ["string", "null"], "format": "uuid" }, "salience": { "type": "number", "minimum": 0, "maximum": 1, "default": 0.5 }, "justification": { "type": "string", "minLength": 10, "maxLength": 300 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["item_id", "created"], "properties": { "item_id": {"type": "string"}, "created": {"type": "boolean"}, "reinforced_existing": {"type": "boolean"} } }` |
| **Required authorization** | Project write (owner scope) + feature allow-list |
| **Required project scope** | Yes |
| **Validation rules** | Kind enum; content 3–500 chars; concept id scope-checked; **duplicate-fact protection:** content hash upsert — a repeated fact *reinforces* (salience/last_reinforced update) rather than duplicating |
| **Side effects** | Upserts a learning-context item (+ activity record) |
| **Idempotency** | Natural key `(project, kind, content-hash)` — idempotent under model retries |
| **Audit** | Full record incl. justification, resulting item id, created vs reinforced |
| **Failure behavior** | Validation failure → `validation_error` with field errors (one retry); context store failure → `execution_error` |

### 2.11 `record_recommendation`

| Aspect | Specification |
|---|---|
| **Purpose** | Allow the AI-driven flows to record a recommendation *draft* whose target was deterministically chosen; dedup prevents nagging |
| **Input JSON schema** | `{ "type": "object", "required": ["kind", "target_concept_ids", "rationale", "justification"], "properties": { "kind": { "type": "string", "enum": ["review_material", "take_quiz", "tutor_session", "revisit_concept", "new_material"] }, "target_concept_ids": { "type": "array", "items": {"type": "string", "format": "uuid"}, "minItems": 1, "maxItems": 5 }, "target_material_id": { "type": ["string", "null"], "format": "uuid" }, "rationale": { "type": "string", "minLength": 10, "maxLength": 600 }, "justification": { "type": "string", "minLength": 10, "maxLength": 300 } }, "additionalProperties": false }` |
| **Output JSON schema** | `{ "type": "object", "required": ["recommendation_id", "status"], "properties": { "recommendation_id": {"type": "string"}, "status": {"type": "string", "enum": ["created", "deduplicated"]}, "dedup_key": {"type": "string"} } }` |
| **Required authorization** | Project write (owner scope) + feature allow-list (recommendation engine; Tutor only when weakness evidence exists in the turn context) |
| **Required project scope** | Yes — concept/material ids scope-checked |
| **Validation rules** | Kind enum; ≤ 5 concepts; rationale length-capped; dedup key derived server-side from `(kind, targets, evidence window)` |
| **Side effects** | Creates recommendation (status `active`) + `RecommendationGenerated` |
| **Idempotency** | Unique among active recommendations per dedup key → `status: deduplicated` return |
| **Audit** | Full record incl. justification and dedup outcome |
| **Failure behavior** | Scope violation → `denied`; storage failure → `execution_error` |

---

## 3. Feature allow-list matrix

| Feature | Tools permitted |
|---|---|
| `tutor` (answering loop) | 1, 2, 3, 4, 5, 6, 7, 8*, 9, 10, 11* — `generate_quiz` only on detected practice intent; `record_recommendation` only with in-turn weakness evidence |
| `quiz_generation` | 1, 4, 5, 7, 8 |
| `learning_context_extractor` (post-turn async) | 9, 10 |
| `recommendation_engine` (async) | 3, 4, 5, 7, 11 |

No feature receives the full catalogue implicitly; matrix changes are reviewed contract changes. The matrix is configuration, validated at startup against the registry.

## 4. Executor enforcement order (per invocation)

```text
1. Feature allow-list check            → denied (security signal if repeated)
2. Scope-injection check               → rejected (tenant id in args) — audit + alert
3. JSON-Schema validation              → validation_error (orchestrator may retry model once)
4. Tool-specific semantic validation   → validation_error (e.g. foreign concept ids → denied)
5. Authorization (read/write policy)   → denied
6. Idempotency / dedup resolution      → replay-or-execute
7. Execution via owning module facade  → (module contract applies; isolation enforced downstream)
8. Result shaping                      → size caps, redaction, DATA-labelling
9. Audit record (always, all outcomes) → tool_invocations trail
```

## 5. Prohibited capabilities (explicit)

`execute_sql` · `database_query` · `arbitrary_http_request` · `filesystem_access` · `shell_execution` · generic code execution · any tool returning other users' data · any tool accepting a caller-supplied `user_id`/`project_id`. The registry rejects registrations of such tools; CI import/contract checks keep them out.

## 6. Justification mapping (PRD §8)

Each PRD §8 interaction maps to tools: search materials → 1, 2 · learning progress → 3, 4 · weak areas → 5 · learning context → 6 · assessment history → 7 · quiz generation → 8 · record activity → 9 · persist context → 10 · recommendations → 11. Every FR-40/41/42 control (validation, authorization, schema-checked writes, audit) is enforced by the executor order in §4.
