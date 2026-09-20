# ADR-0016: Object Storage — S3-Compatible, Private by Default

**Status:** DECIDED (Phase 0) · **Criteria basis:** C1, C6, C9, C12 · **Contracts affected:** §M.3 (Materials upload/verify), §M.14 (Platform storage abstraction)

## Decision

**S3-compatible object storage** holds all binary content (source PDFs, rendered page images) in a **private bucket** (block-public-access, server-side encryption). The application interacts through the Platform storage abstraction (§M.14): presigned PUT for uploads, short-lived presigned GET with `Content-Disposition: attachment` for downloads, HEAD/verify on confirmation, delete on material/account removal. **No PDF binary blobs in PostgreSQL** — the DB stores only keys, checksums, sizes, page counts, and status (metadata strictly separated from content).

## Requirements mapping

| Requirement | Mechanism |
|---|---|
| Private PDF storage | Private bucket + SSE + non-public ACLs; no object ever world-readable |
| Presigned uploads | Server-generated keys (`projects/{project_id}/{uuid}.pdf` — client never chooses the path); policy-constrained content-type + size; short expiry (config, e.g. 15 min) |
| Secure downloads | Short-lived presigned GET, attachment disposition, download URLs expire in minutes; page-image previews likewise expiring |
| Checksum tracking | SHA-256 computed on confirm + verified against declared; stored on the material; duplicate-upload detection by `(project_id, checksum)` |
| Metadata separate from binaries | Postgres `materials`/`material_pages` rows only; binary always in object storage |
| No blobs in DB | Enforced by design — bytea/large-object paths never used; backup sizes stay sane; DB restores stay fast |

## Options considered

### Option 1 — S3-compatible object storage ✅ (MinIO locally; R2/S3-class hosted)
- **Advantages:** presigned-URL flow keeps bytes off the API process (ADR-0008); lifecycle rules (infrequent-access tiering) are config; durable, cheap at prototype scale; identical API surface from laptop to production (C12).
- **Disadvantages:** browser must reach the storage endpoint (CORS + TLS on the bucket endpoint); presign/verify logic must be correct (client honesty not assumed — magic bytes + size + checksum verified server-side).

### Option 2 — Local filesystem (persistent volume)
- **Advantages:** zero setup.
- **Disadvantages:** breaks statelessness (ADR-0001/§24 statelessness posture — API replicas can't share a disk); no presigned flow → uploads proxy through the API (saturates workers, couples upload latency to API capacity); no lifecycle/durability story; deployment platform volumes are slow/ephemeral. Rejected for anything beyond throwaway experiments.

### Option 3 — Database BLOBs (bytea / large objects)
- **Advantages:** one system.
- **Disadvantages:** bloats backups and connection memory; slow streaming; contradicts the storage-abstraction contract; explicitly rejected by the requirements of this ADR.

### Option 4 — CDN-backed storage with public objects + signed-cookie auth
- **Advantages:** fast global delivery.
- **Disadvantages:** public-read posture is wrong for private learner material; complexity unjustified at prototype scale; page-image delivery is low-volume. Rejected; CDN in front of the *frontend* only (ADR-0019).

## Environments

| Aspect | Development (PROTOTYPE ONLY) | Production/prototype deployment |
|---|---|---|
| Implementation | **MinIO** container in Compose (ADR-0019 local stack) | Managed S3-compatible (Cloudflare R2 / AWS S3 / platform equivalent) — choice at deploy time, config-only swap |
| Bucket posture | Private bucket emulated; policy enforcement identical | Private + block-public + SSE + versioning (versioning FUTURE TRIGGER for object-restore drills) |
| Credentials | Seeded dev keys via `.env.development` (placeholders in `.env.example`) | Secrets manager / platform env injection only |
| Endpoint | `http://minio:9000` inside the Compose network | HTTPS endpoint; TLS mandatory |
| Lifecycle rules | None | IA-tiering after ~90 days (A-06 retention), versioning Phase 1 |
| Upload size/page caps | Config caps generous for course PDFs (A-18) | Same caps, enforced at presign **and** re-checked on confirm |

## Verification pipeline (contract §M.3, not yet implemented)

`create_upload_intent` → presigned PUT → client uploads directly → `confirm_upload` → server HEADs the object (exists, size matches), verifies **magic bytes `%PDF`** (never trust declared content-type/extension), computes/compares SHA-256 → material row `queued` + `MaterialUploaded` event atomically (§E). Failure at any verification step → typed `UploadNotVerified`, object left for cleanup reconciliation.

## Scaling triggers (revisit when)

| # | Trigger | Response |
|---|---|---|
| T1 | Page-image preview traffic becomes latency-relevant at distance | CDN in front of a public-read-never bucket via signed URLs / OAC-class integration (config-level) |
| T2 | Compliance requires object-level immutability (legal hold) | Bucket versioning + object lock (Phase 1 posture) |
| T3 | Cross-region DR required (A-14 Phase 2) | Cross-region replication |

## Consequences

- (+) Bytes never touch API/worker memory except in the parsing worker (bounded by caps); storage provider is swappable by config; uploads/downloads scale independently of the API.
- (−) Two endpoints must be publicly reachable (app + storage); presigned correctness is security-critical (covered by upload-verification tests, test-strategy TS2.2); MinIO dev parity is high but not literal-provider parity (scheduled contract check mirrors the AI fixture-drift approach where feasible).
