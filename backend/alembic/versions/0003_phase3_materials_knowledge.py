"""Phase 3 — materials + document ingestion schema (RAG-first foundation).

Review order:
1) pgvector extension
2) tables: materials → documents → document_pages → chunks → chunk_embeddings
3) triggers: touch_updated_at for materials & documents
4) RLS policies (permissive FOR ALL to studycompanion_runtime USING owner_id = app_user_id())
5) runtime-role grants

Design sources:
docs/architecture/database/phase-1-data-model.md,
docs/architecture/architecture-decisions.md (ADR-0013, ADR-0016),
architecture.md (§14 Database Design, §18 RAG Architecture).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

revision = "0003_phase3_materials_knowledge"
down_revision = "0002_phase2_authentication"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"
FN_TOUCH_UPDATED_AT = "touch_updated_at"

T_MATERIALS = "materials"
T_DOCUMENTS = "documents"
T_PAGES = "document_pages"
T_CHUNKS = "chunks"
T_EMBEDDINGS = "chunk_embeddings"

PHASE3_TABLES = [
    T_MATERIALS,
    T_DOCUMENTS,
    T_PAGES,
    T_CHUNKS,
    T_EMBEDDINGS,
]

RLS_POLICIES: list[tuple[str, str]] = [
    (T_MATERIALS, "materials_all_access"),
    (T_DOCUMENTS, "documents_all_access"),
    (T_PAGES, "document_pages_all_access"),
    (T_CHUNKS, "chunks_all_access"),
    (T_EMBEDDINGS, "chunk_embeddings_all_access"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) pgvector extension
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # 2) Tables
    # materials
    op.create_table(
        T_MATERIALS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False, server_default="application/pdf"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="upload_pending"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pipeline_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('upload_pending', 'uploaded', 'processing', 'ready', 'failed')",
            name="ck_materials_status",
        ),
    )
    op.create_index(
        "uq_materials_project_checksum",
        T_MATERIALS,
        ["project_id", "checksum_sha256"],
        unique=True,
    )
    op.create_index("ix_materials_project_status", T_MATERIALS, ["project_id", "status"])
    op.create_index("ix_materials_owner_id", T_MATERIALS, ["owner_id"])

    # documents
    op.create_table(
        T_DOCUMENTS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_MATERIALS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parser_name", sa.Text(), nullable=False, server_default="pymupdf"),
        sa.Column("parser_version", sa.Text(), nullable=False, server_default="1.26.5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="ck_documents_status",
        ),
    )
    op.create_index("ix_documents_material_id", T_DOCUMENTS, ["material_id"])
    op.create_index("ix_documents_project_id", T_DOCUMENTS, ["project_id"])
    op.create_index("ix_documents_owner_id", T_DOCUMENTS, ["owner_id"])

    # document_pages
    op.create_table(
        T_PAGES,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_DOCUMENTS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_MATERIALS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_document_pages_doc_page",
        T_PAGES,
        ["document_id", "page_number"],
        unique=True,
    )
    op.create_index("ix_document_pages_material_page", T_PAGES, ["material_id", "page_number"])
    op.create_index("ix_document_pages_project_id", T_PAGES, ["project_id"])
    op.create_index("ix_document_pages_owner_id", T_PAGES, ["owner_id"])

    # chunks
    op.create_table(
        T_CHUNKS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_MATERIALS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_DOCUMENTS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "page_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_PAGES}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column(
            "content_tsv",
            sa.dialects.postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
        ),
        sa.Column("pipeline_version", sa.Text(), nullable=False, server_default="v1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "content_type IN ('text', 'table', 'figure_caption', 'code', 'ocr')",
            name="ck_chunks_content_type",
        ),
    )
    op.create_index(
        "ix_chunks_project_material_idx",
        T_CHUNKS,
        ["project_id", "material_id", "chunk_index"],
    )
    op.create_index("ix_chunks_document_page", T_CHUNKS, ["document_id", "page_id"])
    op.create_index("ix_chunks_owner_id", T_CHUNKS, ["owner_id"])
    op.create_index("chunks_tsv_idx", T_CHUNKS, ["content_tsv"], postgresql_using="gin")

    # chunk_embeddings
    op.create_table(
        T_EMBEDDINGS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "chunk_id",
            sa.Uuid(),
            sa.ForeignKey(f"{T_CHUNKS}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False, server_default="v1"),
        sa.Column("dimension", sa.Integer(), nullable=False, server_default="1536"),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_chunk_embeddings_chunk_model",
        T_EMBEDDINGS,
        ["chunk_id", "model", "model_version"],
        unique=True,
    )
    op.create_index("ix_chunk_embeddings_project_id", T_EMBEDDINGS, ["project_id"])
    op.create_index("ix_chunk_embeddings_owner_id", T_EMBEDDINGS, ["owner_id"])
    # HNSW index for cosine distance similarity
    conn.execute(
        text(
            f"CREATE INDEX chunk_emb_hnsw ON {T_EMBEDDINGS} "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
        )
    )

    # 3) Triggers (touch_updated_at)
    conn.execute(
        text(f"""
        CREATE TRIGGER trg_materials_touch_updated_at
            BEFORE UPDATE ON {T_MATERIALS}
            FOR EACH ROW
            EXECUTE FUNCTION {FN_TOUCH_UPDATED_AT}();
        """)
    )
    conn.execute(
        text(f"""
        CREATE TRIGGER trg_documents_touch_updated_at
            BEFORE UPDATE ON {T_DOCUMENTS}
            FOR EACH ROW
            EXECUTE FUNCTION {FN_TOUCH_UPDATED_AT}();
        """)
    )

    # 4) Row-Level Security
    for tbl in PHASE3_TABLES:
        conn.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"))

    for tbl, policy_name in RLS_POLICIES:
        conn.execute(
            text(f"""
            CREATE POLICY {policy_name} ON {tbl}
                FOR ALL
                TO {ROLE_RUNTIME}
                USING (owner_id = {FN_APP_USER}())
                WITH CHECK (owner_id = {FN_APP_USER}());
            """)
        )

    # 5) Permissions
    for tbl in PHASE3_TABLES:
        conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO {ROLE_RUNTIME};")
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop grants & RLS policies
    for tbl, policy_name in RLS_POLICIES:
        conn.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {tbl};"))

    for tbl in PHASE3_TABLES:
        conn.execute(text(f"REVOKE ALL ON {tbl} FROM {ROLE_RUNTIME};"))

    # Drop triggers
    conn.execute(text(f"DROP TRIGGER IF EXISTS trg_documents_touch_updated_at ON {T_DOCUMENTS};"))
    conn.execute(text(f"DROP TRIGGER IF EXISTS trg_materials_touch_updated_at ON {T_MATERIALS};"))

    # Drop tables in reverse FK order
    op.drop_table(T_EMBEDDINGS)
    op.drop_table(T_CHUNKS)
    op.drop_table(T_PAGES)
    op.drop_table(T_DOCUMENTS)
    op.drop_table(T_MATERIALS)
