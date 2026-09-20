"""Phase 6 — Concept Mastery Engine schema.

Review order:
1) tables: concept_mastery → mastery_events
2) indexes for per-project/concept queries and audit trail
3) unique constraint on mastery_events (source, source_id, concept_id) for atomic idempotency
4) RLS policies (permissive FOR ALL to studycompanion_runtime USING owner_id = app_user_id())
5) runtime-role grants
6) touch_updated_at trigger on concept_mastery

Design sources:
docs/architecture/module-contracts.md (§7 Mastery),
docs/requirements/requirements-analysis.md (FR-70..74),
docs/architecture/domain-events.md (§2.5 Mastery events).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0006_phase6_mastery"
down_revision = "0005_phase5_assessment"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"
FN_TOUCH_UPDATED_AT = "touch_updated_at"

T_CONCEPT_MASTERY = "concept_mastery"
T_MASTERY_EVENTS = "mastery_events"

PHASE6_TABLES = [
    T_CONCEPT_MASTERY,
    T_MASTERY_EVENTS,
]

RLS_POLICIES: list[tuple[str, str]] = [
    (T_CONCEPT_MASTERY, "concept_mastery_all_access"),
    (T_MASTERY_EVENTS, "mastery_events_all_access"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) concept_mastery — current mastery state per (project, concept)
    op.create_table(
        T_CONCEPT_MASTERY,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mastery_probability",
            sa.Float(),
            nullable=False,
            server_default="0.20",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incorrect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("algorithm_version", sa.String(32), nullable=False, server_default="bkt-1.0"),
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
            "mastery_probability >= 0.0 AND mastery_probability <= 1.0",
            name="ck_concept_mastery_probability",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_concept_mastery_confidence",
        ),
        comment="Current mastery state per (project, concept). RLS: owner_id = app_user_id()",
    )
    op.create_index(
        "uq_concept_mastery_project_concept",
        T_CONCEPT_MASTERY,
        ["project_id", "concept_id"],
        unique=True,
    )
    op.create_index("ix_concept_mastery_project_owner", T_CONCEPT_MASTERY, ["project_id", "owner_id"])
    op.create_index("ix_concept_mastery_concept_id", T_CONCEPT_MASTERY, ["concept_id"])
    op.create_index("ix_concept_mastery_owner_id", T_CONCEPT_MASTERY, ["owner_id"])

    # 2) mastery_events — immutable audit trail of learning updates
    op.create_table(
        T_MASTERY_EVENTS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mastery_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("concept_mastery.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False, server_default="assessment"),
        sa.Column("source_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("mastery_before", sa.Float(), nullable=False),
        sa.Column("mastery_after", sa.Float(), nullable=False),
        sa.Column("confidence_before", sa.Float(), nullable=False),
        sa.Column("confidence_after", sa.Float(), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("algorithm_version", sa.String(32), nullable=False, server_default="bkt-1.0"),
        sa.Column(
            "occurred_at",
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
        comment="Immutable evidence-to-mastery audit trail. RLS: owner_id = app_user_id()",
    )
    # Unique constraint prevents double-application of same evidence
    op.create_index(
        "uq_mastery_events_source_concept",
        T_MASTERY_EVENTS,
        ["source", "source_id", "concept_id"],
        unique=True,
    )
    op.create_index("ix_mastery_events_project_owner", T_MASTERY_EVENTS, ["project_id", "owner_id"])
    op.create_index("ix_mastery_events_concept_id", T_MASTERY_EVENTS, ["concept_id"])
    op.create_index("ix_mastery_events_source_source_id", T_MASTERY_EVENTS, ["source", "source_id"])
    op.create_index("ix_mastery_events_occurred_at", T_MASTERY_EVENTS, ["occurred_at"])

    # 3) touch_updated_at trigger for concept_mastery
    for tbl in [T_CONCEPT_MASTERY]:
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

    # 4) Enable RLS & create policies
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

    # 5) Grants to runtime role
    for tbl in PHASE6_TABLES:
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
    for tbl in [T_CONCEPT_MASTERY]:
        conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{tbl}_touch_updated_at ON {tbl};"))

    # Drop tables in reverse dependency order
    for tbl in reversed(PHASE6_TABLES):
        op.drop_table(tbl)
