# Phase 3 Data Model — Materials & Knowledge

**Status:** Implemented (migration `0003_phase3_materials_knowledge`).  
**Principle:** Every table, column, index, and constraint below maps directly to the RAG evidence foundation and multi-tenant project isolation requirements.

---

## 1. `materials`

| Aspect | Design |
|---|---|
| **Purpose** | Learning material asset representation (PDF document) within a Project. |
| **PK** | `id uuid` (UUIDv7, app-generated via `uuid7()`) |
| **Columns** | `project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE`<br>`owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE`<br>`title text NOT NULL`<br>`mime_type text NOT NULL DEFAULT 'application/pdf'`<br>`size_bytes bigint NOT NULL`<br>`storage_key text NOT NULL`<br>`checksum_sha256 text NOT NULL`<br>`page_count int NULL`<br>`status varchar(32) NOT NULL DEFAULT 'upload_pending' CHECK (status IN ('upload_pending', 'uploaded', 'processing', 'ready', 'failed'))`<br>`failure_reason text NULL`<br>`processing_started_at timestamptz NULL`<br>`processed_at timestamptz NULL`<br>`pipeline_version text NULL`<br>`created_at, updated_at timestamptz NOT NULL DEFAULT now()` |
| **Uniqueness** | `uq_materials_project_checksum (project_id, checksum_sha256)` UNIQUE — prevents duplicate document uploads within the same project. |
| **Indexes** | `uq_materials_project_checksum`, `ix_materials_project_status`, `ix_materials_owner_id`. |
| **RLS Policy** | ENABLED. `materials_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (owner_id = app_user_id())`. |

---

## 2. `documents`

| Aspect | Design |
|---|---|
| **Purpose** | Parsed document instance of a material asset. |
| **PK** | `id uuid` (UUIDv7) |
| **Columns** | `material_id uuid NOT NULL REFERENCES materials(id) ON DELETE CASCADE`<br>`project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE`<br>`owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE`<br>`page_count int NOT NULL DEFAULT 0`<br>`parser_name text NOT NULL DEFAULT 'pymupdf'`<br>`parser_version text NOT NULL DEFAULT '1.26.5'`<br>`status varchar(32) NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed'))`<br>`created_at, updated_at timestamptz NOT NULL DEFAULT now()` |
| **Indexes** | `ix_documents_material_id`, `ix_documents_project_id`, `ix_documents_owner_id`. |
| **RLS Policy** | ENABLED. `documents_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (owner_id = app_user_id())`. |

---

## 3. `document_pages`

| Aspect | Design |
|---|---|
| **Purpose** | Durable page-level extraction records for stable citations. |
| **PK** | `id uuid` (UUIDv7) |
| **Columns** | `document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE`<br>`material_id uuid NOT NULL REFERENCES materials(id) ON DELETE CASCADE`<br>`project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE`<br>`owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE`<br>`page_number int NOT NULL` (1-indexed)<br>`text_content text NOT NULL DEFAULT ''`<br>`char_count int NOT NULL DEFAULT 0`<br>`token_count int NOT NULL DEFAULT 0`<br>`created_at timestamptz NOT NULL DEFAULT now()` |
| **Uniqueness** | `uq_document_pages_doc_page (document_id, page_number)` UNIQUE. |
| **Indexes** | `uq_document_pages_doc_page`, `ix_document_pages_material_page`, `ix_document_pages_project_id`, `ix_document_pages_owner_id`. |
| **RLS Policy** | ENABLED. `document_pages_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (owner_id = app_user_id())`. |

---

## 4. `chunks`

| Aspect | Design |
|---|---|
| **Purpose** | Structure-aware retrieval units anchored to source pages. |
| **PK** | `id uuid` (UUIDv7) |
| **Columns** | `project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE`<br>`material_id uuid NOT NULL REFERENCES materials(id) ON DELETE CASCADE`<br>`document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE`<br>`page_id uuid NOT NULL REFERENCES document_pages(id) ON DELETE CASCADE`<br>`owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE`<br>`page_start int NOT NULL`<br>`page_end int NOT NULL`<br>`chunk_index int NOT NULL`<br>`content text NOT NULL`<br>`token_count int NOT NULL DEFAULT 0`<br>`char_count int NOT NULL DEFAULT 0`<br>`section_path text NULL`<br>`content_type varchar(32) NOT NULL DEFAULT 'text' CHECK (content_type IN ('text', 'table', 'figure_caption', 'code', 'ocr'))`<br>`content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`<br>`pipeline_version text NOT NULL DEFAULT 'v1'`<br>`created_at timestamptz NOT NULL DEFAULT now()` |
| **Indexes** | `ix_chunks_project_material_idx (project_id, material_id, chunk_index)`<br>`ix_chunks_document_page (document_id, page_id)`<br>`ix_chunks_owner_id (owner_id)`<br>`chunks_tsv_idx GIN (content_tsv)` |
| **RLS Policy** | ENABLED. `chunks_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (owner_id = app_user_id())`. |

---

## 5. `chunk_embeddings`

| Aspect | Design |
|---|---|
| **Purpose** | Dense semantic vector representations stored via PostgreSQL `pgvector`. |
| **PK** | `id uuid` (UUIDv7) |
| **Columns** | `chunk_id uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE`<br>`project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE`<br>`owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE`<br>`model text NOT NULL`<br>`model_version text NOT NULL DEFAULT 'v1'`<br>`dimension int NOT NULL DEFAULT 1536`<br>`embedding vector(1536) NOT NULL`<br>`created_at timestamptz NOT NULL DEFAULT now()` |
| **Uniqueness** | `uq_chunk_embeddings_chunk_model (chunk_id, model, model_version)` UNIQUE. |
| **Indexes** | `uq_chunk_embeddings_chunk_model`<br>`ix_chunk_embeddings_project_id`<br>`ix_chunk_embeddings_owner_id`<br>`chunk_emb_hnsw HNSW (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)` |
| **RLS Policy** | ENABLED. `chunk_embeddings_all_access FOR ALL TO studycompanion_runtime USING (owner_id = app_user_id()) WITH CHECK (owner_id = app_user_id())`. |
