"""Phase 7 — Growth Engine schema.

Review order:
1) tables: concept_growth → growth_events
2) indexes for per-project/concept queries and audit trail
3) unique constraint on growth_events (project_id, concept_id, source_mastery_event_id) for atomic idempotency
4) RLS policies (permissive FOR ALL to studycompanion_runtime USING owner_id = app_user_id())
5) runtime-role grants
6) touch_updated_at trigger on concept_growth

Design sources:
docs/architecture/module-contracts.md (§M.8 Growth),
docs/requirements/requirements-analysis.md (FR-61..62),
docs/architecture/domain-events.md (Growth events).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0007_phase7_growth"
down_revision = "0006_phase6_mastery"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"
FN_TOUCH_UPDATED_AT = "touch_updated_at"

T_CONCEPT_GROWTH = "concept_growth"
T_GROWTH_EVENTS = "growth_events"

PHASE7_TABLES = [
    T_CONCEPT_GROWTH,
    T_GROWTH_EVENTS,
]

RLS_POLICIES: list[tuple[str, str]] = [
    (T_CONCEPT_GROWTH, "concept_growth_all_access"),
    (T_GROWTH_EVENTS, "growth_events_all_access"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) concept_growth — current trajectory and attention state per (project, concept)
    op.create_table(
        T_CONCEPT_GROWTH,
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
        sa.Column("current_mastery", sa.Float(), nullable=False, server_default="0.20"),
        sa.Column("previous_mastery", sa.Float(), nullable=True),
        sa.Column("short_term_delta", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("long_term_delta", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("trend", sa.String(32), nullable=False, server_default="insufficient_data"),
        sa.Column("short_term_trend", sa.String(32), nullable=False, server_default="insufficient_data"),
        sa.Column("long_term_trend", sa.String(32), nullable=False, server_default="insufficient_data"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attention_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("attention_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("attention_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recent_failure_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("algorithm_version", sa.String(32), nullable=False, server_default="growth-1.0"),
        sa.Column(
            "last_evaluated_at",
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
            "current_mastery >= 0.0 AND current_mastery <= 1.0",
            name="chk_concept_growth_current_mastery",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_concept_growth_confidence",
        ),
        sa.CheckConstraint(
            "attention_score >= 0.0 AND attention_score <= 1.0",
            name="chk_concept_growth_attention_score",
        ),
        comment="Current growth trajectory and attention state per (project, concept). RLS: owner_id = app_user_id()",
    )
    op.create_index(
        "uq_concept_growth_project_concept",
        T_CONCEPT_GROWTH,
        ["project_id", "concept_id"],
        unique=True,
    )
    op.create_index("ix_concept_growth_project_owner", T_CONCEPT_GROWTH, ["project_id", "owner_id"])
    op.create_index("ix_concept_growth_concept_id", T_CONCEPT_GROWTH, ["concept_id"])
    op.create_index("ix_concept_growth_owner_id", T_CONCEPT_GROWTH, ["owner_id"])

    # 2) growth_events — immutable audit trail of growth evaluations
    op.create_table(
        T_GROWTH_EVENTS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "growth_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("concept_growth.id", ondelete="CASCADE"),
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
        sa.Column("source_mastery_event_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_trend", sa.String(32), nullable=True),
        sa.Column("new_trend", sa.String(32), nullable=False),
        sa.Column("previous_attention_score", sa.Float(), nullable=True),
        sa.Column("new_attention_score", sa.Float(), nullable=False),
        sa.Column("previous_mastery", sa.Float(), nullable=True),
        sa.Column("new_mastery", sa.Float(), nullable=False),
        sa.Column("short_term_delta", sa.Float(), nullable=False),
        sa.Column("long_term_delta", sa.Float(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False, server_default="growth-1.0"),
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
        comment="Immutable audit trail of growth evaluations. RLS: owner_id = app_user_id()",
    )
    op.create_index(
        "uq_growth_events_proj_concept_source",
        T_GROWTH_EVENTS,
        ["project_id", "concept_id", "source_mastery_event_id"],
        unique=True,
    )
    op.create_index("ix_growth_events_project_owner", T_GROWTH_EVENTS, ["project_id", "owner_id"])
    op.create_index("ix_growth_events_concept_id", T_GROWTH_EVENTS, ["concept_id"])
    op.create_index("ix_growth_events_source_mastery_event_id", T_GROWTH_EVENTS, ["source_mastery_event_id"])
    op.create_index("ix_growth_events_occurred_at", T_GROWTH_EVENTS, ["occurred_at"])

    # 3) touch_updated_at trigger for concept_growth
    for tbl in [T_CONCEPT_GROWTH]:
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
    for tbl in PHASE7_TABLES:
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
    for tbl in [T_CONCEPT_GROWTH]:
        conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{tbl}_touch_updated_at ON {tbl};"))

    # Drop tables in reverse dependency order
    for tbl in reversed(PHASE7_TABLES):
        op.drop_table(tbl)
