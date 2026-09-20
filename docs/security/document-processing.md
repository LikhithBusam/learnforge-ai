# Security Guidelines for Document Processing

**Status:** Enforced in Phase 3.

---

## 1. Untrusted Input Posture

Uploaded PDFs and document texts are treated strictly as **untrusted data**, not instructions or system commands:
- Any prompt injection patterns (e.g., `"Ignore previous instructions"`, `"System: You are an administrator"`) found in document text remain inert text strings stored in the database.
- Parsers do not execute embedded scripts, macros, or shell commands.
- External URLs extracted from documents are never fetched by the backend parser.

---

## 2. Storage & Upload Hardening

- **Private Buckets:** Object storage buckets (`learning-materials`) remain completely private. No object is ever world-readable.
- **Server-Controlled Paths:** Storage keys are strictly generated on the backend:
  `{space_id}/{project_id}/{material_id}/document.pdf`
  Clients cannot choose or manipulate storage paths.
- **Pre-upload Validation:** MIME type, file extension, and declared size are validated before issuing upload URLs.
- **Pre-ingestion Verification:** Uploaded objects are verified via `HEAD` (existence, non-zero size, `<= MAX_UPLOAD_BYTES`) and verified for `%PDF-` magic bytes.
- **Secret Redaction:** Object storage credentials and signed URLs are never stored in error messages or logs.

---

## 3. Database Isolation (RLS)

All ingestion tables (`materials`, `documents`, `document_pages`, `chunks`, `chunk_embeddings`) enforce PostgreSQL Row-Level Security:
- Policies evaluate `owner_id = app_user_id()`.
- Application queries run under the unprivileged `studycompanion_runtime` role with `NOBYPASSRLS`.
- Cross-project access is blocked at the database engine level.
