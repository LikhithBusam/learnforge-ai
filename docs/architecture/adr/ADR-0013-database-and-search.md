# ADR-0013: Database and Search — PostgreSQL 16 + pgvector + PostgreSQL FTS

**Status:** DECIDED (Phase 0) · **Criteria basis:** C1, C3, C4, C9, C12 dominant · **Supersedes:** deferred "database engine" row in `architecture-decisions.md` · **Isolation compatibility:** ADR-0002 · **Contracts affected:** §M.14 (Platform unit-of-work), §M.4 (Knowledge retrieval), §M.9 (Analytics events)

## Decision

**PostgreSQL 16 is the single system of record** for relational data, vector search (**pgvector**, HNSW index), and full-text search (**`tsvector` + GIN**). One engine, one transaction boundary, one backup story, one isolation story.

| Concern | Implementation direction (design, not yet built) |
|---|---|
| Relational integrity | FKs across learning state (answers → questions → quizzes; mastery events → concepts) |
| RLS | Row-level security policies keyed on a session variable (`app.current_user_id`-style); app connects as a non-superuser, non-`BYPASSRLS` role |
| Project isolation | `project_id` denormalized on tenant tables; RLS predicate + in-query filters (ADR-0002) |
| Vector retrieval | `pgvector` HNSW index (cosine); `project_id` filter **inside the ANN query** — never post-filtered |
| Full-text search | Generated `tsvector` column on chunk content, GIN index; lexical half of hybrid retrieval |
| Transactions / outbox | Domain rows + `outbox_events` commit atomically (ADR-0006); `processed_events` dedup; partial-unique indexes for idempotency keys |
| Migrations | Expand/contract, `lock_timeout` guard, migrations run before app rollout (ADR-0012) |

## Options considered

### Option 1 — PostgreSQL 16 + pgvector + Postgres FTS ✅
- **Advantages:** chunks and their embeddings commit in **one transaction** (no dual-write); the tenant filter lives inside the same query and transaction — exactly what ADR-0002 requires; one security boundary, one backup/PITR story; RLS is native; FTS is free with the DB; async Python driver ecosystem mature; managed offerings with pgvector are commodity (Neon/Supabase/RDS).
- **Disadvantages:** ANN scale ceiling below dedicated engines; FTS weaker than purpose-built engines for exotic ranking; one engine carries all load profiles.

### Option 2 — PostgreSQL + external vector database (Qdrant/Pinecone/Weaviate class)
- **Advantages:** higher recall/throughput at scale; quantization; richer payload filtering; horizontal sharding.
- **Disadvantages:** **dual-write consistency problem** between chunks and vectors (violates ADR-0006's atomicity guarantees — a chunk without its vector or vice versa becomes possible); a **second authorization boundary** to get right in a product whose top invariant is isolation; extra infrastructure, credentials, and cost inside a 4-day window; the retrieval interface in Knowledge would not change, so the benefit is deferred while the cost is immediate.
- **Verdict:** rejected for Phase 0; **deferred with explicit triggers** (§6).

### Option 3 — MongoDB + Atlas Vector Search
- **Advantages:** flexible documents; integrated vector search; managed.
- **Disadvantages:** no native RLS (isolation would live only in application code — **fails criterion C3 / ADR-0002**); weak relational integrity for the mastery/assessment graph; multi-document transactions exist but are a poor fit for the outbox + dedup + partial-unique-index idempotency design; team would re-implement in-query tenant filtering as a convention. Rejected on the isolation invariant alone.

### Option 4 — MySQL / MariaDB
- **Advantages:** ubiquitous, managed everywhere.
- **Disadvantages:** no pgvector-class extension story, weaker JSONB, no native RLS equivalent — fails C3. Rejected.

### Option 5 — SQLite (dev) + Postgres (prod)
- **Advantages:** zero-setup local dev.
- **Disadvantages:** RLS/extension behavior differs → local dev no longer proves isolation, the one thing it must prove; divergent environments contradict C12's "reproducible" clause. Rejected; dev uses containerized Postgres (ADR-0019).

## Decision rationale

C3 (isolation compatibility) dominates: only Postgres satisfies all of {RLS on session variables, filtered ANN inside the transaction, FK integrity, JSONB flexibility} simultaneously. C1/C9 follow: one managed service covers three access patterns, and the outbox/idempotency design (ADR-0006) is native to Postgres semantics (partial unique indexes, skip-locked claiming, advisory locks). Option 2's advantages cannot be exercised within the prototype window, while its costs (dual-write, second boundary) are immediate.

## Why an external vector database is explicitly deferred

The retrieval seam (`KnowledgeService.retrieve_evidence/search`) is the **only** code that would change — embeddings are regenerable from source (pipeline-versioned), and the module contract already isolates the pipeline. Deferring therefore costs nothing now and loses nothing later.

## Migration triggers (measured, not assumed)

Introduce a dedicated vector store when **any** of:

| # | Trigger | Measurement method |
|---|---|---|
| T1 | Sustained corpus > **5M chunks** in a project or in aggregate | `COUNT(chunks)` trend + ingestion forecast |
| T2 | Vector search p95 > **150 ms** at the configured target recall, after HNSW parameter tuning and per-project partial indexes | Latency histogram on the vector-search span (ADR-0020) |
| T3 | A requirement pgvector cannot express: quantization to cut memory cost, multi-tenant ANN sharding, or payload-filter features the retrieval design needs | Requirement review (engineering decision, not a benchmark) |
| T4 | Embedding write throughput during ingestion bursts saturates the primary DB (bulkhead violated at the storage layer) | Ingestion-span + DB write-latency correlation |

Any trigger firing is a reviewed decision recorded as an ADR amendment; the migration is: backfill-embeddings job → dual-read behind the Knowledge facade → cutover → Postgres vectors retired.

## Consequences

- (+) One backup/restore/PITR story; isolation invariant enforced at the same layer that stores the data; fastest correct build.
- (−) HNSW tuning is an operational skill the team owns; scale ceiling is real (T1–T4 exist precisely because of this); FTS ranking quality is adequate but not exceptional — mitigated by hybrid retrieval + rerank (ADR-0003 grounding design).

## Open questions

1. Managed-provider choice (Neon vs Supabase vs RDS-class) is a **deployment concern** resolved in ADR-0019, not here.
2. Exact HNSW parameters (`m`, `ef_construction`, query `ef_search`) start from library defaults and are tuned against the retrieval eval set — values are configuration, not decisions.
