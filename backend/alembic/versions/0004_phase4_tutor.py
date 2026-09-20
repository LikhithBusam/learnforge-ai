"""Phase 4 — AI Tutor & persistent conversation schema.

Review order:
1) tables: conversations → messages → message_citations → learning_context_items
2) triggers: touch_updated_at for conversations, messages, learning_context_items
3) RLS policies (permissive FOR ALL to studycompanion_runtime USING owner_id = app_user_id())
4) runtime-role grants

Design sources:
docs/architecture/module-contracts.md (§5 Tutor),
docs/requirements/requirements-analysis.md (FR-30..36),
architecture.md (§14 Database Design, §18 RAG Architecture).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0004_phase4_tutor"
down_revision = "0003_phase3_materials_knowledge"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"
FN_TOUCH_UPDATED_AT = "touch_updated_at"

T_CONVERSATIONS = "conversations"
T_MESSAGES = "messages"
T_CITATIONS = "message_citations"
T_LEARNING_CONTEXT = "learning_context_items"

PHASE4_TABLES = [
    T_CONVERSATIONS,
    T_MESSAGES,
    T_CITATIONS,
    T_LEARNING_CONTEXT,
]

RLS_POLICIES: list[tuple[str, str]] = [
    (T_CONVERSATIONS, "conversations_all_access"),
    (T_MESSAGES, "messages_all_access"),
    (T_CITATIONS, "message_citations_all_access"),
    (T_LEARNING_CONTEXT, "learning_context_items_all_access"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) conversations
    op.create_table(
        T_CONVERSATIONS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
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
        comment="Persistent conversation sessions for AI Tutor. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_conversations_project_owner", T_CONVERSATIONS, ["project_id", "owner_id"])
    op.create_index("ix_conversations_owner_id", T_CONVERSATIONS, ["owner_id"])

    # 2) messages
    op.create_table(
        T_MESSAGES,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "answer_status",
            sa.String(32),
            nullable=False,
            server_default="grounded",
        ),
        sa.Column("ai_request_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
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
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_role",
        ),
        sa.CheckConstraint(
            "answer_status IN ('grounded', 'insufficient_evidence', 'general_knowledge', 'error')",
            name="ck_messages_answer_status",
        ),
        comment="Tutor conversation turns. RLS: owner_id = app_user_id()",
    )
    op.create_index(
        "ix_messages_conversation_created", T_MESSAGES, ["conversation_id", "created_at"]
    )
    op.create_index("ix_messages_project_id", T_MESSAGES, ["project_id"])
    op.create_index("ix_messages_owner_id", T_MESSAGES, ["owner_id"])
    op.create_index(
        "uq_messages_conversation_idempotency",
        T_MESSAGES,
        ["conversation_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # 3) message_citations
    op.create_table(
        T_CITATIONS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        comment="Validated RAG citations backing tutor responses. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_message_citations_message", T_CITATIONS, ["message_id"])
    op.create_index("ix_message_citations_chunk", T_CITATIONS, ["chunk_id"])
    op.create_index("ix_message_citations_project_id", T_CITATIONS, ["project_id"])
    op.create_index("ix_message_citations_owner_id", T_CITATIONS, ["owner_id"])

    # 4) learning_context_items
    op.create_table(
        T_LEARNING_CONTEXT,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("concept_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("salience", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(32), nullable=False, server_default="user"),
        sa.Column(
            "last_reinforced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
            "kind IN ('goal', 'preference', 'weakness', 'strength', 'note')",
            name="ck_learning_context_items_kind",
        ),
        comment="Persistent learner context items for project personalization. RLS: owner_id = app_user_id()",
    )
    op.create_index(
        "ix_learning_context_project", T_LEARNING_CONTEXT, ["project_id", "owner_id"]
    )
    op.create_index("ix_learning_context_owner", T_LEARNING_CONTEXT, ["owner_id"])

    # 5) touch_updated_at triggers
    for tbl in [T_CONVERSATIONS, T_MESSAGES, T_LEARNING_CONTEXT]:
        conn.execute(
            text(
                f"""
                CREATE TRIGGER trg_{tbl}_touch_updated_at
                BEFORE UPDATE ON {tbl}
                FOR EACH ROW
                EXECUTE FUNCTION {FN_TOUCH_UPDATED_AT}();
                """
            )
        )

    # 6) Enable RLS & create policies
    for tbl, pol_name in RLS_POLICIES:
        conn.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"))
        conn.execute(text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;"))
        conn.execute(
            text(
                f"""
                CREATE POLICY {pol_name}
                ON {tbl}
                FOR ALL
                TO {ROLE_RUNTIME}
                USING (owner_id = {FN_APP_USER}())
                WITH CHECK (owner_id = {FN_APP_USER}());
                """
            )
        )

    # 7) Grants to runtime role
    for tbl in PHASE4_TABLES:
        conn.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO {ROLE_RUNTIME};")
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Revoke grants & drop policies
    for tbl, pol_name in RLS_POLICIES:
        conn.execute(text(f"REVOKE ALL ON TABLE {tbl} FROM {ROLE_RUNTIME};"))
        conn.execute(text(f"DROP POLICY IF EXISTS {pol_name} ON {tbl};"))

    # Drop triggers
    for tbl in [T_CONVERSATIONS, T_MESSAGES, T_LEARNING_CONTEXT]:
        conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{tbl}_touch_updated_at ON {tbl};"))

    # Drop tables in reverse order
    for tbl in reversed(PHASE4_TABLES):
        op.drop_table(tbl)
