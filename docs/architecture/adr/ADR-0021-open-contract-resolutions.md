# ADR-0021: Resolutions of Open Contract Questions

**Status:** DECIDED (this stage) · **Method:** each question resolved strictly against existing requirements and architecture documents; no requirement is invented, no prior decision silently changed — the resolved decisions *amend* the contracts listed per question and the change log at the end records every edit.

---

## Q1. Dedup-registry ownership — who owns the consumer-side idempotency registry (`processed_events`)?

**Question.** Background consumers need a dedup registry (at-least-once delivery → idempotent consumption). The module contracts assigned it to Analytics; the alternative was Jobs. Which module owns it?

**Relevant requirements.** NFR-02 (retryable operations must not create duplicate state), FR-74 (event processing with duplicate handling + idempotency), §12 eventing requirements; module-contracts §M.9 (Analytics "non-responsibilities: business decisions") and §M.13 (Jobs "non-responsibilities: business logic"); ADR-0006 (transactional outbox + consumer-side idempotency); ADR-0014 (durable record in Postgres).

**Options.**
1. **Analytics-owned** — Analytics stores event-consumption state as part of its ingestion mandate; Jobs stays pure transport.
2. Jobs-owned — Jobs tracks consumption for everything it dispatches; a single infrastructure owner for all dedup.
3. Each consumer module owns its own registry table — maximal autonomy, maximal duplication.

**Decision.** **Analytics owns the registry** (option 1), with a precise scope clarification: the registry keys on `(consumer, event_id)` and is written **inside each consumer's own transaction** (dedup-check + work + registry-insert atomically) — Analytics provides the table, schema, and access contract, not a runtime service in the hot path. Jobs never consults it.

**Rationale.** The registry is *event-consumption state*, and Analytics is already the only module permitted to observe all events (module-contracts §M.9); giving it the registry keeps Jobs business-free (its contract forbids logic) while avoiding per-module registry tables. Writing inside the consumer's transaction is what actually guarantees exactly-once *effects* under at-least-once *delivery* (ADR-0006) — a remote "dedup service" in Analytics would introduce a distributed-transaction problem the design exists to avoid. Option 3 was rejected because shared schema + shared query patterns are one thing to get right instead of fourteen.

**Consequences.** Analytics gains one more responsibility in its contract (registry stewardship — schema + ingest-time dedup semantics); every consumer's transaction now includes a registry insert; Analytics' own batch ingestion uses the same mechanism (dogfooding). Jobs' contract unchanged.

**Reversibility.** Moderate: the table is small and keyed simply; moving ownership later means a table rename + consumer insert update (mechanical), not a workflow redesign.

**Required documentation changes.** module-contracts §M.9 (responsibility + command surface), §M.13 (idempotency row clarified), domain-events §1 (delivery-semantics note).

---

## Q2. Does `TutorInteractionCreated` contribute mastery evidence?

**Question.** Tutor turns produce signals (repeated misconception questions, self-reported confusion, concept exploration). Should Mastery consume `TutorInteractionCreated` as evidence, or should mastery derive only from assessments?

**Relevant requirements.** FR-60 (mastery estimate evolving with evidence — sources not restricted to quizzes), FR-31 (Tutor understands assessment history *and* learning context), FR-63 (persistent learning context incl. "significant Tutor context"), PRD §13's learning workflows; module-contracts §M.7 (evidence `source` enum already includes `tutor_signal`), §M.5; domain-events §2.3 (event payload already carries `concept_ids_touched`, `answer_status`, sufficiency meta); ADR-0005 (deterministic learning logic — mastery math is code over evidence).

**Options.**
1. **Yes — weak tutor signals become low-strength mastery evidence.**
2. No — mastery from assessments only; tutor data flows to learning context instead.
3. Yes — tutor signals weighted equally with quiz answers.

**Decision.** **Yes, but structurally weak (option 1):** Mastery consumes `TutorInteractionCreated` only where the payload carries an explicit, machine-derived signal (`answer_status` + concept touched + sufficiency), maps it to `source='tutor_signal'` with a **fixed, config-declared evidence strength strictly below any quiz answer's** (initial mapping: e.g. grounded answer on a weak concept = small positive exploration signal; repeated confusion pattern = routed to Growth's `MistakeRepeated`, not to mastery). The *weights are configuration* (ADR-0005 posture) and are tuned/validated against the mastery trajectory fixtures before arming. Tutor free-text is never evidence — the event payload rule (§E: no content) is unchanged.

**Rationale.** FR-60 requires mastery to evolve with evidence and does not restrict sources; §13's repeated-mistake workflow already routes tutor-derived patterns to learning context/recommendations, so *behavioral* response exists regardless. A modest tutor signal makes mastery responsive in projects where the learner engages mostly with the Tutor (a real PRD §6 flow), while strict sub-quiz weighting preserves the deterministic, assessment-anchored character of mastery (ADR-0005; risk R-10 mitigation — mastery must not mislead). Option 3 was rejected because unvalidated conversational signals would make the estimate noisy and R-10 likely; option 2 was rejected because it makes FR-60's "evolves with evidence" narrower than the PRD's Tutor-centric usage flows.

**Consequences.** Mastery's events-consumed list gains `TutorInteractionCreated` (already anticipated as "optional" in the contract); a fixed strength mapping table is a config artifact; the mastery trajectory fixture set gains a tutor-signal family; eval note: mastery math unchanged (same pure function, new evidence rows).

**Reversibility.** High: it is a consumer + a config mapping; removing it returns to assessment-only evidence with no schema impact (evidence trail already records source).

**Required documentation changes.** module-contracts §M.7 (events consumed, evidence-input description), domain-events §2.3 (consumers list), golden-dataset §6 (fixture family), assumptions A-22-style note for the mapping (recorded in assumptions.md as A-23).

---

## Q3. `pending_review` assessment lifecycle — who resolves low-confidence gradings?

**Question.** When open-ended grading falls below confidence, the result is flagged `pending_review`. Is there a resolution workflow (re-grade job, admin resolution), or is the flag terminal-for-the-prototype with admin visibility only?

**Relevant requirements.** FR-53/FR-54 (AI evaluation of open answers, explanatory feedback — with honest degradation, principles §16); NFR-01 (graceful handling of invalid AI output); evaluation-strategy §2.7 (pending_review rate is a health metric); risk R-11 (unfair/inconsistent grading); module-contracts §M.6 (AnswerResultDto/QuizResultDto carry `pending_review`); A-01/A-05 (admin read-only over learner content).

**Options.**
1. **Flag + explicit user-visible provisional feedback; auto re-grade once via the event chain; admin view only.**
2. Admin resolution workflow (admin re-grades) — violates A-01/A-05 posture.
3. Silent auto re-grade until confident — hides degradation from the learner, contradicts principles §16.

**Decision.** **Option 1, concretely:** (a) the learner sees the feedback explicitly marked **provisional** (first-class UI state, never a confident wrong score); (b) an **async re-grading task** (learning queue, idempotent, dedup-keyed per answer, max 1 extra attempt) runs after `AssessmentEvaluated(graded_by='ai', confidence < threshold)` — a re-grade that lands above confidence updates the result and emits `AssessmentEvaluated` again (schema carries `attempt`); (c) if still below confidence, the grade stays `pending_review` **and is excluded from mastery evidence until resolved** (no low-confidence data polluting the deterministic math); (d) the admin AI-evaluation view lists pending grades as a health metric. **No admin mutation of grades** (A-01 preserved). The confidence threshold itself is `TBD — calibrated with the evaluation dataset`.

**Rationale.** NFR-01 requires defined degraded behaviour, not silence; principles §16 requires honesty (provisional must be visible); ADR-0006's event chain gives the re-grade mechanism for free (one more idempotent consumer); excluding unresolved low-confidence grades from mastery protects FR-60/R-10 integrity. Options 2/3 were rejected on A-01 and honesty grounds respectively.

**Consequences.** Assessment gains one idempotent consumer (re-grader); `AssessmentEvaluated` payload gains `attempt` + `supersedes_answer_evaluation`; mastery's evidence ingestion ignores `pending_review` rows (rule stated in §M.7); quiz results surface a "may update" note for pending items; one new eval-observability metric (pending-resolution rate).

**Reversibility.** High: the re-grader is one consumer; turning it off returns to flag-only posture (which the contract already supported).

**Required documentation changes.** module-contracts §M.6 (commands + failure modes + events), §M.7 (evidence rule), domain-events §2.4 (`AssessmentEvaluated` payload + consumers), evaluation-strategy §2.7 (lifecycle note), traceability FR-53 row.

---

## Q4. Materials ↔ Jobs status callback design

**Question.** How does Materials learn of pipeline status transitions (processing/ready/failed) — via its own service methods called by worker tasks (one-way dependency into Materials), or by consuming its own emitted events back?

**Relevant requirements.** FR-21/FR-23 (status pipeline user-visible), FR-26 (retry/failure handling), §M.3's "must NOT access directly" and one-way dependency rules; §M.13 (tasks are thin delegations); ADR-0001 (module seams); ADR-0014 (queue topology).

**Options.**
1. **Worker tasks call Materials service methods** (`begin_processing`, `mark_completed`, `mark_failed`) — status authority stays in Materials.
2. Materials consumes its own events back (event-sourced status) — symmetric event flow, but self-consumption for state the module owns.
3. Jobs writes material status directly — makes Jobs a business actor (contract violation).

**Decision.** **Option 1 — worker tasks invoke Materials service methods.** The pipeline task's *whole job* is: call Materials to begin (advisory guard + status), drive Knowledge ingestion, call Materials to complete/fail. Materials remains the single **status authority** (only it transitions its state machine), the dependency direction stays one-way (worker → Materials → Knowledge), and `MaterialProcessingStarted/Completed/Failed` are emitted by Materials **inside those service methods** (one transaction each), so events remain truthful records of state the module actually took — not parallel bookkeeping.

**Rationale.** A module's state machine should not be event-sourced *from itself* (option 2 adds a hop where a direct transaction exists and risks event/state divergence — the exact dual-write class ADR-0006 exists to kill). Option 3 breaks §M.13's non-responsibility. Option 1 also keeps the "one processing run at a time" guard inside Materials where the state lives.

**Consequences.** §M.3's public interface gains three internal-mode status-transition commands (worker/ownership-context callers only, not HTTP-exposed); §M.9/§E unaffected (events still emitted by Materials); pipeline task shape documented as a Jobs-side task registration calling these methods in order.

**Reversibility.** Low-cost: the three commands are narrow; an event-driven rework later would only change the task body.

**Required documentation changes.** module-contracts §M.3 (interface + transaction boundary rows), §M.13 (task registration example note), traceability FR-21/FR-23 rows (unchanged mapping, clarified mechanics).

---

## Q5. Admin error posture — 403 vs 404

**Question.** For unauthorized access: learner-facing non-owned resources already return 404 (no existence disclosure, ADR-0002). What should the admin plane return for a **non-admin** principal hitting `/admin/*`? And what does an admin get for a nonexistent target?

**Relevant requirements.** NFR-04 (secure APIs), FR-02/FR-03; ADR-0002 (404-not-403 rationale: avoid confirming existence); module-contracts §M.10 (authorization row: "Forbidden (non-admin — existence of the plane is not secret at this level)"); principles §1/§12; threat model T13 (insider abuse — audited admin reads).

**Options.**
1. **404 for non-admin on `/admin/*`** — uniform with the tenant posture; the admin surface is not secret, but hiding it costs nothing and removes an enumeration/probing signal.
2. 403 for non-admin — explicit "you lack the role"; slightly better DX for developers, worse for attackers.
3. Mixed (404 for routes, 403 for actions) — inconsistent, error-prone.

**Decision.** **404 everywhere for role failures (option 1), 404 for nonexistent targets too — with one exception:** *authentication succeeds but role check fails* on an admin route → **404** (no confirmation the admin plane exists); *nonexistent target for a legitimate admin* → **404** (ordinary not-found). Explicit **403 is reserved for authenticated, correctly-scoped requests to operations the role could in principle hold but a policy denies** (e.g. a write-tool denial returned to the model as data, rate-limit/budget denials). In short: **identity/existence questions → 404; capability/policy questions → 403.** Every admin-route denial is audit-logged (T13 monitoring needs the signal even with 404 — the audit event carries the attempted route and principal; anomaly alerting keys on audit volume, not on client-visible codes).

**Rationale.** The 404 rule's purpose (don't disclose existence) applies *more* to a platform-wide read plane than to a user's own resources. Uniformity also simplifies the authorization test matrix (one rule for role failures) and keeps error-code semantics meaningful for the cases where 403 carries real information. Option 2's developer convenience is served by the audit log and staging logs instead.

**Consequences.** §M.10's failure-mode row is corrected (it previously said `Forbidden` for non-admin — the one place the 404 posture wasn't yet applied; this ADR fixes that inconsistency rather than introducing a new posture); authorization tests add admin-route 404 cases; audit-logging on denial becomes mandatory (previously implied).

**Reversibility.** Trivial (status-code mapping + tests).

**Required documentation changes.** module-contracts §M.10 (failure modes + authorization), §M.12 (denial posture note for tools: 403-as-data to the model unchanged), test-strategy TS2.5 (case addition), project-principles §12 (wording), contract-traceability FR-03/NFR-04 rows.

---

## Change log (documents amended by this ADR)

| Document | Change |
|---|---|
| `module-contracts.md` | §M.3 (+3 internal status-transition commands, transaction note), §M.6 (+re-grade consumer, failure modes, pending-review mastery exclusion), §M.7 (+`TutorInteractionCreated` consumed with weak-signal rule; pending evidence exclusion), §M.9 (+registry stewardship), §M.10 (404 posture), §M.13 (idempotency clarification, task-shape note), open-questions section marked resolved → ADR-0021 |
| `domain-events.md` | §2.3 consumers (+Mastery), §2.4 `AssessmentEvaluated` payload (+`attempt`, `supersedes_answer_evaluation`) + consumers (+re-grader), §1 dedup note (registry owner) |
| `architecture-decisions.md` | Index note pointing ADR-0021 |
| `test-strategy.md` | TS2.5 admin-route 404 cases |
| `project-principles.md` | §12 wording (404 vs 403 rule) |
| `contract-traceability.md` | Rows for FR-03, FR-21/23, FR-53/60, NFR-04 |
| `evaluation-strategy.md` | §2.7 pending-review lifecycle note |
| `golden-dataset.md` | §6 tutor-signal fixture family |
| `assumptions.md` | A-23 (tutor-signal strength mapping), A-24 (pending-review confidence threshold TBD) |
