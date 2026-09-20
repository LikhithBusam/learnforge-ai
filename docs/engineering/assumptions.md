# Engineering Assumptions — AI Study Companion

**Status:** Planning artifact for review.
**Rule:** Every value or decision not explicitly specified by the PRD is recorded here. An unstated assumption is the main source of architecture drift; a stated one is a reversible decision. No assumption below contradicts the PRD; each fills a documented gap. If the PRD is later supplied in full text, this table is re-validated against it.

> **Process assumption P-0:** The PRD file itself is not present in this repository. The only repository artifact is `architecture.md`, an architecture baseline that quotes and cites PRD v3.0 (Candidate Challenge Edition) section-by-section. This analysis treats that baseline's PRD citations as the requirements source of truth and **does not invent PRD content beyond them**. If the actual PRD text is supplied, every entry below must be re-validated against it. — *Why required:* the analysis task must have an authoritative source. *Impact:* low, provided the baseline's citations are faithful. *Changeable:* yes — a full re-validation pass is required when the PRD text arrives.

Each entry: **ID · Assumption · Why required · Impact · Changeable later?**

---

## Process & scope

| ID | Assumption | Why it is required | Impact | Changeable later |
|---|---|---|---|---|
| P-0 | PRD text not in repo; analysis derives requirements from `architecture.md`'s PRD citations | An analysis cannot proceed without a source of truth | Low — flagged everywhere; re-validation pass required if PRD text arrives | Yes |
| P-1 | MoSCoW priorities follow PRD §18's stated Must/Should/Nice levels; where the baseline does not enumerate item-by-item, the call is derived from section context and flagged as judgment (requirements-analysis §9) | MoSCoW classification is required by the task; the PRD's per-item list is not fully quoted | Medium — affects cut order under scope pressure | Yes — a review pass confirms the flagged calls |

## Product & authorization

| ID | Assumption | Why it is required | Impact | Changeable later |
|---|---|---|---|---|
| A-01 | Admin is **read-only** over learner content. PRD §16 says administrators "inspect" and calls the panel lightweight | Removes an entire class of privilege-escalation/destruction risk; admin queries can later route to a read replica | Medium — admin cannot mutate learner data; moderation flows would need a new design | Yes — mutating admin requires approvals + audit reason codes |
| A-02 | Admin role is assigned out-of-band (seed/migration), not self-service | PRD names "authorized administrators" but specifies no promotion flow; self-service admin is a vulnerability | Low — ops procedure for granting admin | Yes — invitation flow later |
| A-03 | Self-hosted email/password authentication (no external IdP) | §18 requires auth but names no provider; avoids a vendor dependency in the critical login path for a 4-day build | Medium — we own password storage, reset, session security; migration to OIDC must remain localized (single Principal resolution point) | Yes — swap token verification only if Principal abstraction is honoured |
| A-04 | Email verification is stubbed in Phase 0 (account usable immediately; flag recorded); enforced Phase 1 | No email provider specified; blocking the demo on mail delivery is poor prototype judgment | Low — a stubbed flow + Phase 1 work item | Yes |
| A-05 | Admins see learning **metadata and analytics**, not raw documents or free-text answers | §16's goals are satisfiable without exposing content; data minimization is a privacy default | Low — break-glass content access would need audit reason codes | Yes |
| A-16 | One learner per project; no sharing/collaboration | Nothing in the PRD suggests multi-user projects; assuming otherwise would complicate every isolation control | High if wrong — collaboration requires membership tables and reworking isolation predicates everywhere | No (cheap) — it is an isolation-model redesign; flagged as a deliberate future decision, not a toggle |

## AI subsystem

| ID | Assumption | Why it is required | Impact | Changeable later |
|---|---|---|---|---|
| A-07 | Providers/models are chosen by **role** in configuration, not named in domain code; per-role fallback exists | §14 explicitly leaves providers/models open ("left to the candidate"); lock-in inside domain code is the costliest AI mistake | Low — a thin abstraction may not expose vendor-unique features; adopting one is a deliberate interface change | Yes — any provider mix via config |
| A-08 | Context budget shares start ≈55% evidence / 20% conversation / 15% learning context / 10% learner state | A budget must exist (FR-64, §11); a magic ratio in code would be an invisible assumption | Low — tuning knob, calibrated against the Tutor eval suite | Yes — configuration |
| A-15 | English-language material; `english` FTS configuration in Phase 0 | PRD gives no language requirement; text-search configuration must be chosen | Medium if multilingual materials appear — needs per-material language detection or multilingual embeddings | Yes — pipeline_versioned reprocessing |
| A-17 | Cost figures are **estimates** from a configured price table, labelled as estimates in the UI | Providers change prices; §14 asks for estimated cost | Low — reconcile against billing exports in Phase 1 | Yes |
| A-20 | Retrieval sufficiency thresholds (τ, min supporting chunks, top-k, rerank depth) start as configured defaults, tuned against a labelled eval set | §7 requires a sufficiency decision; values cannot be guessed in code and must be measurable | Medium — over-conservative thresholds refuse answerable questions; under-conservative admit weak evidence | Yes — config + eval gate |
| A-21 | A labelled evaluation set (answerable + deliberately unanswerable questions over sample materials) is constructed during the build | FR-83/FR-84 evaluation and the CI regression gate need fixtures; PRD requires evaluation but supplies no dataset | Medium — eval quality bounds regression-gate quality | Yes — grows over time |
| A-22 | Structured-output failure policy: one bounded repair attempt, then a documented per-feature fallback (skip question / pending_review grading / template recommendation) | FR-42 requires validation before persistence; a failure policy must be defined per feature | Low — deterministic, auditable | Yes — per-feature policy |
| A-23 | Tutor-signal mastery evidence mapping: explicit machine-derived signals only, fixed config-declared strength strictly below any quiz answer; free text never evidence | FR-60 says mastery evolves with evidence without restricting sources; ADR-0021/Q2 chose weak signals; the strength *values* are not specified by the PRD and must not be guessed into code | Low-Medium — mis-weighting would skew mastery (R-10); trajectory fixtures validate before arming | Yes — config; re-validated against fixtures |

## Data, retention & operations

| ID | Assumption | Why it is required | Impact | Changeable later |
|---|---|---|---|---|
| A-06 | Retention: activity events 12 months hot; AI request detail 90 days (then aggregated); conversations compacted at 180 days; audit 12 months hot | No retention requirements given; balances "persistent context" (§2) against cost and privacy | Low — all values are configuration, not code | Yes — set from legal input in production |
| A-09 | No regulated data category (health, financial, minors) | PRD describes general skill learning | Medium if wrong — regulated data would require DPA review, consent management, residency decisions | Yes — flagged as a launch-blocking review |
| A-10 | Latency targets (e.g. upload confirm < 500 ms, TTFT < 2.5 s, retrieval pipeline < 800 ms) are engineering targets with stated bases — not measured SLOs | No performance requirements in the PRD; regressions still need baselines to be detectable | Low — replaced by measurements once load testing exists | Yes |
| A-11 | Sized for low hundreds of concurrent users in Phase 0 | No user counts given; sizing justifies the monolith/single-DB choices | Medium if wildly wrong — the scaling path (§24-style) handles growth | Yes — revisit at phase gates |
| A-12 | Availability: ~99% Phase 0; 99.9% Phase 1 for the **core loop only**, AI features excluded | No availability target in the PRD; promising uptime on third-party model providers would be dishonest | Low — sets deploy/redundancy posture | Yes |
| A-13 | Phase 0 deploys to a managed container platform, not Kubernetes; everything containerized so the migration is a manifest change | §18 requires public deployment inside the build window; K8s would consume disproportionate budget | Low — containerization is non-negotiable; platform is swappable | Yes |
| A-14 | RPO/RTO: 24 h/4 h Phase 0; 15 min/1 h Phase 1; quarterly restore drills | No DR requirements given; backup method choice needs targets | Low — validated or corrected by drills | Yes |
| A-18 | Upload policy caps (max bytes, max pages) are configuration with Phase 0 defaults generous enough for real course PDFs | §15 requires secure document handling; caps must exist to bound worker resource use | Low — config | Yes |
| A-19 | OCR escalation path: native extraction first, Tesseract-class OCR second, vision model only for pages both fail | §5 requires handling scanned pages/diagrams/tables; cost-ordering must be deliberate | Low — pipeline stage ordering; vision model selection is config | Yes |

## Resolved ambiguities (ambiguity → chosen resolution)

The task asked for ambiguities requiring explicit assumptions. Consolidated mapping:

| Ambiguity in PRD (as cited) | Resolution |
|---|---|
| No identity provider specified (§18) | A-03: self-hosted auth |
| Admin capabilities described as "inspect" only (§16) | A-01, A-05: read-only, metadata-level |
| Exact models/providers left to the candidate (§14) | A-07: role-based config, fallback chains |
| No retention, RTO/RPO, availability, or user-count figures anywhere | A-06, A-14, A-12, A-11 |
| No performance requirements beyond "appropriate for a prototype" (§15) | A-10: engineering targets + measurement method |
| No evaluation dataset provided (§14) | A-21: constructed golden sets during the build |
| No email provider specified | A-04: verification stubbed Phase 0 |
| No language requirement for materials | A-15: English first |
| Thresholds for sufficiency unspecified (§7) | A-20: config tuned against eval |
| Collaboration/multi-user projects unmentioned | A-16: single learner per project |

| A-24 | Pending-review grading confidence threshold (re-grade trigger + mastery-exclusion boundary) | FR-53/NFR-01 require defined degraded behaviour for low-confidence AI grading (ADR-0021/Q3); the threshold value is not specified by the PRD | Low — a mis-set threshold either over- or under-flags provisional feedback; rate is a health metric | Yes — `TBD — to be calibrated using the evaluation dataset` |

---

## Register maintenance rules

1. **No silent assumptions.** Any implementation decision not covered by the PRD gets an ID here before the code exists.
2. Assumptions are **reversible by design** — each entry states its change path; changing one updates this file in the same PR.
3. Assumptions that graduate into requirements (e.g. by PRD amendment) move to `requirements-analysis.md` and are removed here.
4. Every assumption surfaced in code review or testing gets re-checked against this register — drift means the register failed, not the reviewer.
