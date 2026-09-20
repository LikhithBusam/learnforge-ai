# AI Evaluation Strategy — AI Study Companion

**Status:** Strategy for review (revised: explicit structural-vs-semantic gate taxonomy, §1.1/§4). **No thresholds are invented** — where a number is not yet evidence-backed it is marked `TBD — to be calibrated using the evaluation dataset` (assumptions A-20/A-21 in `docs/engineering/assumptions.md`). **No results are claimed** — nothing has been run; this document defines *how* we will measure, never *what we measured*. **No semantic metric is ever claimed to be 100% accurate.**

**Why this exists (requirements):** FR-83 (evaluate Tutor, Retrieval, Assessment, Recommendations on named metrics), FR-84 (prompt/model/retrieval changes can regress → regression evaluation), FR-35 (unsupported-question handling is a core evaluation requirement). Evaluation ships with the product, not as a side project (project-principles §8–10, §16).

---

## 1. Architecture of evaluation

Three layers, per the requirements analysis:

| Layer | When | Gate? |
|---|---|---|
| **L1 — Offline regression suite** | CI, on any change to prompts, models, retrieval strategy, chunking, or thresholds | **Yes — merge gate** (delta vs stored baseline) |
| **L2 — Online sampling** | Continuous in production: a configured fraction of real AI requests re-scored asynchronously | No (trend + alert) |
| **L3 — Human review** | Ad hoc via admin dashboard; also builds labelled ground truth | No (calibrates L2; arbitrates L1 disputes) |

**Metric storage:** every evaluation result is persisted (suite, metric, score, method: `rule | model | human`, details) linked to the AI request and to the prompt/model/pipeline versions under test — a regression is attributable to the change that caused it (FR-84).

**Baseline discipline:** a suite's first accepted run defines its stored baseline. Subsequent runs compare against the baseline within a configured delta; any change to the baseline itself is a reviewed decision recorded in the evaluation log. Baselines start empty — they are populated by the *first real run* on the golden dataset, never pre-filled.

**Model-based judging rule:** where a metric cannot be computed by code (e.g. "does this explanation actually address the question?"), a model judge is used — with a rubric, a structured output schema, and its own agreement measured against human labels before its scores gate anything. A judge that has not demonstrated agreement with human labels never gates a merge.

**Environment rule:** L1 in CI uses recorded fixtures and deterministic seeds; no live provider calls in the merge gate. A separate scheduled job runs live-provider contract checks so fixture drift is detected.

---

## 1.1 Gate taxonomy — structural hard gates vs semantic evaluation

Every evaluation check belongs to exactly one of two classes. Mixing them (a semantic metric treated as provably correct, or a structural rule left un-armed) is a design defect in this document.

### Class A — Structural hard gates

**Definition:** checks whose expected outcome is fully determined by the system's own rules and data — computable by code, no model judgment, no labels required. They are **armed from day one** with **zero tolerance**: any failure blocks merge and is treated as a **defect**, not a metric dip.

| Structural hard gate | What it asserts | Where enforced |
|---|---|---|
| Schema validity | Every AI structured output parses against its declared schema before persistence/state change | §2.6; principle §4; unit + CI |
| Project scope | Every retrieval, tool call, and job operates only within the injected `ProjectScope`; cross-tenant assertion never trips | Isolation suite (test-strategy TS2.6); tool-contract executor order |
| Authorization | Role/ownership/allow-list matrices hold on every route, tool, and admin read; denials audited | TS2.5; tool-contracts §4 |
| Citation **presence when required** | A grounded answer carries ≥ 1 citation; an insufficiency response carries none presented as evidence | §2.4 (structural sub-checks) |
| Citation **references an actual retrieved source** | Every citation marker resolves to a chunk that was retrieved in that turn, within scope | §2.4 (structural sub-checks); citation validator |
| Recommendation references **valid concepts** | Target concept ids exist, are in scope, and belong to the evidence-justified set; dedup honored | §2.9 (structural sub-checks) |
| Deterministic mastery calculation | Update math matches hand-computed trajectories; order-independent; range/NaN invariants hold | §2.8 (property tests) |
| Idempotency | Redelivered events, replayed idempotency keys, duplicate submissions produce no duplicate state | test-strategy TS2.10 |
| Sufficiency-gate consistency | Given the same scores/config, the gate's decision is reproducible (the *threshold value* is semantic tuning; the *mechanism* is structural) | §2.2 |
| Fabrication in refusal | An insufficiency response contains no substantive claims beyond "materials cover X / suggestions" | §2.5 (structural sub-check) |

### Class B — Semantic evaluation

**Definition:** metrics that judge **quality of language or ranking** — requiring human labels and/or validated model judgment. Their thresholds are **always** `TBD — to be calibrated using the evaluation dataset` until real runs produce distributions; they are **never claimed to be 100%**; they gate merges only after calibration (delta vs stored baseline), and a model-judge scores them only after demonstrating agreement with human labels.

| Semantic evaluation | Judged by | Threshold status |
|---|---|---|
| Answer quality (relevance, completeness) | model-judge + human labels | TBD — to be calibrated using the evaluation dataset |
| Groundedness (claims supported by cited sources) | model-judge + human labels | TBD — to be calibrated using the evaluation dataset |
| Citation correctness (the cited source actually **supports the claim**; page attribution beyond containment) | human labels; model-judge where agreed | TBD — to be calibrated using the evaluation dataset |
| Retrieval quality (recall/nDCG/MRR, sufficiency agreement) | deterministic math **over human labels** (labels are the judgment) | TBD — to be calibrated using the evaluation dataset |
| Assessment quality (rubric agreement, coverage F1, feedback actionability, consistency) | human labels + model-judge | TBD — to be calibrated using the evaluation dataset |
| Quiz question quality (answerability, distractors, difficulty) | model-judge + human labels | TBD — to be calibrated using the evaluation dataset |
| Recommendation usefulness (relevance, actionability) | model-judge + human labels | TBD — to be calibrated using the evaluation dataset |
| Refusal behavior quality (false-refusal rate, near-miss handling) | human labels + model-judge on near-miss band | TBD — to be calibrated using the evaluation dataset |

**Consequence of the taxonomy:** a failing **structural** gate means "the system is broken" (fix the code); a failing **semantic** gate means "quality moved" (tune/rollback the change, review the baseline). CI treats them differently: structural gates block unconditionally from day one; semantic gates block only on calibrated-threshold breaches or baseline deltas.

---

## 2. Evaluation areas

### 2.1 Tutor answer quality

| Aspect | Definition |
|---|---|
| **What is evaluated** | The final Tutor message for a grounded turn: relevance to the question, pedagogical quality (explanation, examples, simpler restatement when asked), completeness given the evidence |
| **Input** | Golden tutor case: question + project context ref + retrieved evidence set + generated answer (full turn replay) |
| **Expected behavior** | Answer addresses the question using the supplied evidence; follows conversation conventions; tone appropriate; no invented facts beyond evidence; follows-ups handled |
| **Evaluation metric** | `answer_relevance` (model-judged rubric 0–1: addresses the actual question); `completeness_given_evidence` (model-judged: key evidence points used); `hallucination_rate` (rule: claims without citation markers in a grounded answer) |
| **Evaluation method** | Rule-based checks first (structure, status field, citation presence); model-judge rubric scoring for relevance/completeness on the answerable subset |
| **Pass/fail criteria** | `hallucination_rate` = **0 tolerance** on the grounded subset (any unsupported claim fails the case); `answer_relevance` ≥ `TBD — to be calibrated using the evaluation dataset`; regression gate: no suite metric drops more than the configured delta vs baseline (`delta` itself `TBD — to be calibrated`) |
| **Human evaluation requirement** | Initial labelling of the golden set; periodic arbitration of judge disagreements; every prompt-version bump sampled |
| **Regression testing approach** | L1 gate on golden tutor cases; per-prompt-version trending in L2; failures block merge with a per-case diff |

### 2.2 Retrieval quality

| Aspect | Definition |
|---|---|
| **What is evaluated** | The retrieval pipeline (hybrid search → fusion → rerank) for a query against a project corpus, independent of answer generation |
| **Input** | Golden retrieval case: query + corpus ref + labelled relevant chunks (with relevance grades) |
| **Expected behavior** | Relevant chunks ranked above irrelevant ones; top-k contains the labelled evidence; exact-term queries (acronyms, formulas) retrieved by the lexical half; paraphrase queries by the dense half |
| **Evaluation metric** | `recall@k`, `ndcg@k` (k = config values used in production, not eval-specific); `mrr`; `sufficiency_precision/recall` (does the sufficiency gate's decision agree with labels) |
| **Evaluation method** | Rule-based ranking metrics computed against labels — **fully deterministic**, no model judge |
| **Pass/fail criteria** | `recall@k` ≥ `TBD`; `ndcg@k` ≥ `TBD`; sufficiency gate agreement ≥ `TBD` — all to be calibrated; structural floor: every golden case must retrieve its labelled *primary* chunk in the top-k before baseline calibration can even be attempted |
| **Human evaluation requirement** | Labelling relevant chunks/pages per query (the main labelling cost); adjudicating "partially relevant" grades |
| **Regression testing approach** | L1 gate; per-change diffs showing which cases moved and in which half (dense vs lexical) of the pipeline |

### 2.3 Groundedness

| Aspect | Definition |
|---|---|
| **What is evaluated** | Whether claims in a grounded answer are supported by the cited evidence chunks |
| **Input** | Generated answer + its citation set + the retrieved chunks (claim-by-claim decomposition) |
| **Expected behavior** | Every factual claim maps to ≥ 1 cited chunk that actually supports it; no claim rests on chunk content that is absent or contradicts it |
| **Evaluation metric** | `groundedness` (supported claims / total claims); `claim_decomposition_coverage` (all claims identified and checked) |
| **Evaluation method** | Rule layer: every citation marker resolves to a retrieved chunk (hard check). Claim-support judgement: model-judge with rubric against chunk excerpts, **agreement-validated against human labels before gating** |
| **Pass/fail criteria** | Hard rule: citation markers must resolve to retrieved chunks (100%, structural). `groundedness` ≥ `TBD — to be calibrated`; any claim contradicted by its cited chunk = case failure regardless of score |
| **Human evaluation requirement** | Label claim-support on the golden answers; periodic re-calibration of the judge |
| **Regression testing approach** | L1 gate + L2 sampling of production turns; groundedness trended per prompt/model version |

### 2.4 Citation correctness

| Aspect | Definition |
|---|---|
| **What is evaluated** | Split by the gate taxonomy (§1.1): *structural* — citations exist where required and reference actually-retrieved sources; *semantic* — whether the cited source genuinely supports the cited claim (correctness of the citation's content and page attribution beyond mechanical containment) |
| **Input** | Answer's citation list + retrieval metadata + chunk records |
| **Expected behavior** | Structural: every `[n]` resolves to a retrieved, in-scope chunk; grounded answers carry citations; insufficiency responses present none as evidence. Semantic: quoted text actually supports the claim; document title + page number are the right source (the "Document — Page N" contract, FR-34) |
| **Evaluation metric** | Structural: `citation_presence` (required citations present — zero tolerance); `citation_resolves_to_retrieved` (markers → retrieved in-scope chunks — zero tolerance). Semantic: `citation_support_correctness` (citations whose source supports the claim / total); `page_attribution_accuracy` |
| **Evaluation method** | Structural sub-checks: **purely rule-based** (marker resolution, scope membership) — deterministic, no model judge. Semantic sub-checks: human labels on the golden set; model-judge for support correctness once judge agreement with labels is demonstrated |
| **Pass/fail criteria** | Structural: **100% required, armed from day one** — a single unresolved/missing citation fails the case and the run (the pre-generation validator should have downgraded the answer; if an invalid structural citation reaches evaluation, the validator has a defect — a bug, not a metric dip). Semantic: `citation_support_correctness` ≥ `TBD — to be calibrated using the evaluation dataset`; never claimed 100% |
| **Human evaluation requirement** | None for the rule itself; human review samples page-image links (rendering correctness) |
| **Regression testing approach** | L1 gate; also unit-level property tests on the validator (§ test-strategy) |

### 2.5 Unsupported-question handling (refusal correctness)

| Aspect | Definition |
|---|---|
| **What is evaluated** | Behavior on questions the project's materials do not answer — the PRD's explicit core requirement (FR-35) |
| **Input** | Golden unanswerable case: question + corpus ref where the topic is genuinely absent (+ near-miss corpus variants) |
| **Expected behavior** | Pre-generation sufficiency gate routes to the insufficiency path; response explicitly states the materials don't cover it; names what *is* covered where applicable; offers suggested actions; **no fabricated content**; general-knowledge offer clearly labelled and only on opt-in |
| **Evaluation metric** | `refusal_correctness` (refused correctly / unanswerable cases); `false_refusal_rate` (answerable cases wrongly refused — from the tutor answerable subset); `fabrication_rate` (**must be 0**: any substantive claim emitted in an insufficiency response that is not a "materials cover X" statement) |
| **Evaluation method** | Rule-based on answer status field + content checks; model-judge only for the "near-miss" band (topic tangentially related) where rule checks are ambiguous |
| **Pass/fail criteria** | `fabrication_rate` = **0 tolerance**; `refusal_correctness` ≥ `TBD`; `false_refusal_rate` ≤ `TBD` (both calibrated; near-miss cases may carry a deliberately lower bar, recorded per-case) |
| **Human evaluation requirement** | High: the unanswerable/near-miss labelling is judgment-heavy; humans own the labels, rules only check consistency |
| **Regression testing approach** | L1 gate — this suite blocks merge on any fabrication; near-miss band trends separately so tightened gates don't silently increase false refusals |

### 2.6 Quiz generation quality

| Aspect | Definition |
|---|---|
| **What is evaluated** | Generated questions: answerable from the cited source chunks, single defensible answer (MCQ), plausible distractors, difficulty ≈ requested band, correct typing/structure |
| **Input** | Structured generation output + the concept's source chunks + requested concept/difficulty |
| **Expected behavior** | Question is grounded in provided chunks (provenance ids valid); MCQ has exactly one defensible correct option among plausible distractors; open-ended has a usable rubric; difficulty matches the requested band; **schema validity** |
| **Evaluation metric** | `structured_output_validity_rate` (rule); `question_answerability` (model-judge vs chunks); `single_answer_defensibility` (model-judge); `difficulty_calibration` (predicted vs requested band); `distractor_plausibility` (model-judge) |
| **Evaluation method** | Rule layer: schema, provenance id validity, MCQ structural checks. Model-judge for answerability/defensibility/distractors (rubric-scored, human-validated) |
| **Pass/fail criteria** | `structured_output_validity_rate` ≥ `TBD` (floor 95% in alerting rules — calibration pending); quality metrics ≥ `TBD`; hard rule: a question whose provenance chunk ids don't resolve in scope is rejected at generation time (structural, 0 tolerance) |
| **Human evaluation requirement** | Label a question-quality subset; calibrate the judge; periodic review of difficulty calibration |
| **Regression testing approach** | L1 gate on generation golden cases; adaptivity evaluated separately (§2.8) |

### 2.7 Assessment grading quality

| Aspect | Definition |
|---|---|
| **What is evaluated** | Open-ended grading against rubrics: score accuracy, concept coverage identification (covered/missing), feedback quality (explanatory, FR-54), consistency across re-runs |
| **Input** | Golden assessment case: question + rubric + student answer + human-labelled expected grading |
| **Expected behavior** | Score within tolerance of human label; concepts covered/missing match labels; feedback names reasoning errors rather than only a score; deterministic temperature/params |
| **Evaluation metric** | `rubric_agreement` (score agreement with human labels, e.g. within-tolerance rate — tolerance `TBD`); `concept_coverage_f1` (covered/missing sets vs labels); `feedback_actionability` (model-judged rubric); `grading_consistency` (same input re-graded N times → score variance below `TBD`) |
| **Evaluation method** | Agreement metrics vs human labels (primary); model-judge only for feedback quality; consistency by repeated deterministic runs |
| **Pass/fail criteria** | `rubric_agreement` ≥ `TBD`; `concept_coverage_f1` ≥ `TBD`; hard rule: grading below the confidence threshold must be flagged `pending_review` (structural — flagged status is checked, the threshold value is `TBD — to be calibrated`) |
| **Human evaluation requirement** | Core: human-labelled gradings are the ground truth; double-labelling on disputed cases; judge recalibration when rubrics change |
| **Regression testing approach** | L1 gate; L2 samples real gradings for agreement drift; pending_review rate monitored as a health metric (rate spike = model/prompt drift signal) |

### 2.8 Mastery updates

| Aspect | Definition |
|---|---|
| **What is evaluated** | The deterministic update math: correctness of BKT-style + decay computation under evidence sequences; convergence/order-independence; difficulty weighting; edge cases (contradictory evidence, long gaps, no evidence) |
| **Input** | Synthetic evidence sequences with hand-computed expected mastery trajectories |
| **Expected behavior** | Correct answers with strong evidence raise mastery (bounded); wrong answers lower it; decay reduces stale mastery; **replay in any event order converges to the same state**; output stays in [0,1] with valid confidence |
| **Evaluation metric** | `trajectory_exact_match` (computed vs expected within floating tolerance); `order_independence` (permutation invariance — hard requirement); `invariant_violations` (range/NaN/negative-confidence checks — must be 0) |
| **Evaluation method** | **Purely deterministic unit/property tests** — no AI involved; this area is code, not model (ADR-0005) |
| **Pass/fail criteria** | Hard: `order_independence` and `invariant_violations` at 100%/0; trajectory fixtures match within tolerance `TBD` (numeric tolerance, calibrate when fixtures are authored) |
| **Human evaluation requirement** | None (mathematical); reviewers approve the expected trajectories |
| **Regression testing approach** | Property-based tests in L1 on every change to the math; parameters (weights/decay) are config — parameter changes re-run the full fixture set and require reviewed baseline updates |

### 2.9 Recommendations

| Aspect | Definition |
|---|---|
| **What is evaluated** | Targeting (deterministic logic) and content (AI phrasing): relevance to weaknesses/goals, actionability (names a concrete artifact — material, concept, quiz), non-repetition |
| **Input** | Golden recommendation case: learner state (weaknesses, mistakes, goal, materials) + generated recommendation |
| **Expected behavior** | Target concept is justified by the provided state; rationale references the actual evidence; a concrete next action is named; no duplicate of an existing active recommendation |
| **Evaluation metric** | Structural (§1.1): `target_validity` (targets exist, in scope, ∈ evidence-justified set — deterministic logic must be correct, it's code); `dedup_honored` (no duplicate active recommendation). Semantic: `relevance` (model-judged vs state); `actionability` (model-judged: names artifact + verb) |
| **Evaluation method** | Structural: **deterministic rules**, armed day one. Semantic: model-judge rubric (human-validated) |
| **Pass/fail criteria** | Structural: `target_validity` = 100%, dedup violations = 0. Semantic: relevance/actionability ≥ `TBD — to be calibrated using the evaluation dataset` (never claimed 100%) |
| **Human evaluation requirement** | Label relevance on a recommendation subset; review template-fallback outputs for respectfulness/clarity |
| **Regression testing approach** | L1 gate; L2 samples accepted/dismissed recommendations (dismissal rate is the real-world relevance signal — tracked, not gated) |

---

## 3. Suites, gates, and cadence summary

| Suite | Golden cases | Gate | Cadence | Stored-baseline rule |
|---|---|---|---|---|
| Tutor (answer quality, groundedness, citations, refusal) | § golden-dataset tutor cases | Merge gate | Every prompt/model/retrieval change | First run defines baseline; deltas reviewed |
| Retrieval | retrieval cases | Merge gate | Every retrieval/chunking/threshold change | Same |
| Assessment (generation, grading) | assessment cases | Merge gate | Every generation/grading prompt change | Same |
| Adaptivity | deterministic selection fixtures | Merge gate | Every selection-policy change | Exact-match (pure code) |
| Mastery math | property tests + trajectories | Merge gate | Every math/config change | Exact-match (pure code) |
| Recommendations | recommendation cases | Merge gate | Every recommendation change | Same |
| Online sampling (all suites) | production traffic sample | Alert only | Continuous | Trend vs trailing window |

**CI mechanics (conceptual):** eval job runs after unit/integration gates; artifacts = per-case results + metric summary + diff vs baseline; a gate failure blocks merge and prints the offending cases. Per the taxonomy (§1.1): **structural hard gates block unconditionally from day one**; **semantic gates arm only after threshold calibration** — `TBD` entries are empty config constants until then. A structural failure is filed as a defect; a semantic failure is a quality regression to tune or rollback.

## 4. Threshold register (single source of truth)

### 4.1 Structural hard gates — armed from day one, zero tolerance

| Structural gate | Requirement | Status |
|---|---|---|
| Schema validity of AI structured outputs | 100% parse before persistence | **Armed: zero tolerance** |
| Project scope (retrieval, tools, jobs) | No cross-tenant access; scope assertion never trips | **Armed: zero tolerance** |
| Authorization matrices (routes, tools, admin) | All denials correct + audited | **Armed: zero tolerance** |
| Citation presence when required | Grounded answers cite; refusals don't present citations as evidence | **Armed: zero tolerance** |
| Citation resolves to an actual retrieved source | Every marker → retrieved, in-scope chunk | **Armed: zero tolerance** |
| Recommendation references valid concepts (+ dedup honored) | 100% valid targets; 0 dedup violations | **Armed: zero tolerance** |
| Deterministic mastery calculation | Trajectories match; order-independent; invariants hold | **Armed: zero tolerance** |
| Idempotency surfaces | No duplicate state under redelivery/replay | **Armed: zero tolerance** |
| Fabrication in insufficiency responses | 0 substantive claims beyond coverage statements | **Armed: zero tolerance** |
| Provenance of generated questions | Source chunk ids resolve in scope | **Armed: zero tolerance** |

### 4.2 Semantic evaluation — `TBD` until calibrated; never claimed 100%

| Semantic metric | Threshold | Status |
|---|---|---|
| `answer_relevance` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `completeness_given_evidence` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `groundedness` (claims supported by cited sources) | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `citation_support_correctness` / `page_attribution_accuracy` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `recall@k` / `ndcg@k` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `sufficiency gate agreement` (with labels) | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `refusal_correctness` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `false_refusal_rate` | ≤ ? | TBD — to be calibrated using the evaluation dataset |
| `structured_output_validity_rate` (quality trend; the hard schema gate above is separate) | ≥ ? (alert floor ~95%) | TBD — to be calibrated using the evaluation dataset |
| `question_answerability` / `single_answer_defensibility` / `distractor_plausibility` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `rubric_agreement` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `concept_coverage_f1` | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| `grading_consistency` variance | ≤ ? | TBD — to be calibrated using the evaluation dataset |
| `relevance` / `actionability` (recommendations) | ≥ ? | TBD — to be calibrated using the evaluation dataset |
| Regression delta vs baseline (semantic suites) | ≤ ? | TBD — to be calibrated (config) |

**Calibration procedure (when the dataset exists):** run the suite → collect metric distributions → set thresholds at a defensible operating point (e.g. near the observed-good band, tightened over time) → record each threshold + its rationale in this register → arm the gate. Thresholds only tighten absent incident; loosening one is a reviewed decision.
