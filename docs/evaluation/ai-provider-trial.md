# AI Provider Trial Protocol — Evidence-Based Selection

**Status:** Methodology for the ADR-0015 addendum decision (which vendor/model fills each capability role). **Nothing here is a benchmark result.** All current-pricing, capability, and availability fields for real candidates are marked `Needs verification at build kickoff` until verified against provider documentation/billing at trial time. The protocol below is the *experiment design*; results get recorded in the trial log it defines.

**Selection principle:** candidates are compared **by role**, not by provider brand — a vendor may win one role and lose another, and different roles may land on different vendors (ADR-0015 explicitly supports this via role-based config).

---

## 1. Candidate profile sheet (per role × candidate)

Every candidate is documented with this sheet **before** trial runs; any field that cannot be verified from provider docs or a smoke call at trial time stays marked `Needs verification at build kickoff` — **never guessed**:

| Field | Notes |
|---|---|
| Model/provider | Role under trial (see §2) |
| Role | generation · structured generation · embeddings · reranking · evaluation/judge · document/vision |
| Input limits | Context window (tokens), max input size for embeddings/rerank batches, image size/page limits for vision — `Needs verification at build kickoff` |
| Output characteristics | Streaming yes/no, max output tokens, JSON/schema mode support, typical verbosity — `Needs verification at build kickoff` |
| Pricing basis | Per-token input/output bands, per-1k-embeddings, per-request rerank — recorded **from the provider's current price page at trial time**; never from memory or folklore |
| Availability | Region/endpoint posture, SLA if any, rate-limit tiers — `Needs verification at build kickoff` |
| API characteristics | SDK/REST, auth model, batch endpoints, latency posture (TTFT class) — `Needs verification at build kickoff` |
| Structured-output support | Native schema/JSON mode? guaranteed syntax? — verified with a smoke call against our Pydantic schemas |
| Streaming support | SSE/chunked deltas; interleave with tool-call channel? — smoke-call verified |
| Embedding dimensions | Fixed dimension + matryoshka/truncation support where applicable — `Needs verification at build kickoff` |
| Known limitations | From provider docs (knowledge cutoffs, rate caps, output caps, no-schema modes) — `Needs verification at build kickoff` |
| Data/privacy considerations | Retention defaults, training-on-inputs posture, zero-retention options, data-residency options — recorded from provider terms; procurement requirement per the baseline (no-training terms preferred) |

---

## 2. Roles and candidate shortlist shape

Shortlists are finalized at build kickoff (2–3 candidates per role is sufficient for a decision); the table defines what each role demands so shortlists can be assembled from verified data:

| Role | Trial focus | Non-negotiable capability |
|---|---|---|
| Generation (tutor answering) | Answer quality + grounding discipline + streaming latency | Streaming; long-context; follows the citation contract |
| Structured generation (grading, questions, extraction, recommendation phrasing) | Schema validity + rubric faithfulness at temperature 0 | JSON/schema mode; deterministic params |
| Embeddings | Retrieval quality (recall/nDCG on the retrieval cases) + batch cost | Fixed dimension consistent with schema; batching |
| Reranking | Precision improvement over fused order (nDCG@top-6 delta) | Score-only API over (query, passage) pairs |
| Evaluation/judge | Agreement with human labels on golden sets | Structured rubric output; temperature 0 |
| Document/vision | Page-image extraction quality on the scanned/figure corpus docs | Structured page content output |

**Note on role-sharing:** the `evaluate` (judge) role may trial the same model as `generation.reasoning` — the trial data (agreement with human labels) decides, not convenience.

---

## 3. Golden-set trial method (repeatable experiment format)

**Preconditions:** golden dataset v1 authored per `golden-dataset.md` (corpus ingested, cases labelled, labels with provenance); trial harness runs the *real* pipeline code paths with the candidate plugged into the Gateway adapter — never a side-channel demo script.

**Experiment unit:** one `(role, candidate, dataset_version, trial_config)` run. Each run records: dataset version, prompt versions, temperature/params, per-case outputs, per-case metric scores, usage metadata (tokens, latency, TTFT), and estimated cost from the configured price table. Runs are **repeatable**: same inputs + temperature-0/params → comparable outputs; generation roles are run N=3 where variance matters (consistency metric).

### 3.1 Hard gates (candidate disqualified on any failure — these are pass/fail, not scores)

| Hard gate | Check |
|---|---|
| Invalid JSON / schema failure | Structured outputs must parse against the declared Pydantic schema; repeated failure (beyond the one repair attempt) on > a small verified-sample count disqualifies for structured roles |
| Unauthorized tool request | Any attempt to invoke a non-allow-listed tool, or to supply a tenant id in tool arguments — security disqualifier |
| Fabricated citation | Any citation marker not resolving to a retrieved chunk in the same turn |
| Unsupported answer when refusal is required | Any substantive claim emitted on an unanswerable golden case instead of the insufficiency path |
| Missing required output fields | Structured outputs missing contract-required fields |
| Scope violation | Any output referencing content outside the injected project scope |

Hard-gate failures are recorded per-case and are **not averaged** — one fabricated citation in the refusal set is disqualifying regardless of other scores.

### 3.2 Comparative metrics (candidates ranked; thresholds not required for *comparison*)

| Dimension | Metric (from evaluation-strategy, same definitions) | Applies to roles |
|---|---|---|
| Answer quality | `answer_relevance`, `completeness_given_evidence` (model-judge scored, judge fixed across candidates so comparison is apples-to-apples) | generation |
| Groundedness | `groundedness` (supported claims / total claims) | generation, structured |
| Citation correctness | `citation_support_correctness`, `page_attribution_accuracy` (semantic layer; structural layer is a hard gate) | generation |
| Refusal behavior | `refusal_correctness`, `false_refusal_rate`, near-miss band behavior | generation |
| Structured output validity | `structured_output_validity_rate` + repair-attempt rate | structured, vision, judge |
| Retrieval quality | `recall@k`, `ndcg@k`, `mrr` (embeddings); nDCG delta over fused order (rerank) | embeddings, rerank |
| Assessment grading agreement | `rubric_agreement`, `concept_coverage_f1`, `grading_consistency` (N-run variance) | structured (grading) |
| Recommendation quality | `relevance`, `actionability` (targets are deterministic — not model-dependent) | generation.mid |
| Latency | TTFT p50/p95 (generation), end-to-end p50/p95 per operation | all |
| Token usage | Tokens in/out per case, per suite | all |
| Estimated cost | Price-table estimate per suite run + projected per-user-day cost at assumed volumes (labelled estimate, A-17) | all |
| Failure rate | Timeout / 429 / 5xx rates over the trial window | all |

### 3.3 Trial procedure (repeatable)

1. **Smoke pass** per candidate: auth, streaming, schema mode, batch endpoints, rate limits (fills the profile sheet's `Needs verification` fields).
2. **Suite runs** per role: candidate → run the applicable golden suites via the Gateway (hard gates evaluated first; disqualified candidates stop here).
3. **Scoring:** comparative metrics computed by the same rule/judge implementations for every candidate (fixed judge version across candidates).
4. **Cost model:** per-suite cost × projected daily volumes (A-11 sizing) → estimated monthly band per candidate; recorded with the price-page snapshot date.
5. **Decision record:** ADR-0015 addendum — per role: chosen candidate, runner-up, trial artifacts reference, price snapshot date, profile sheets attached. Runner-up stays configured as the fallback role where feasible.
6. **Re-trial triggers:** major model-version change by the incumbent, sustained quality-metric regression in L2 sampling, or cost anomaly trend.

### 3.4 What the trial does NOT do

- It does not tune prompts per candidate beyond the documented prompt versions (a candidate that needs bespoke prompts to pass is recorded as such — portability cost is a selection factor).
- It does not fabricate or extrapolate benchmark numbers; unmeasured fields stay marked.
- It does not gate the merge pipeline — this is a build-kickoff selection experiment, distinct from CI evaluation gates.
