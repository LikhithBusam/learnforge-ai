"""Phase 8 — Recommendation Engine schema.

Review order:
1) tables: recommendations → recommendation_feedback
2) indexes for per-project/concept queries and active recommendation lookups
3) RLS policies (permissive FOR ALL to studycompanion_runtime USING owner_id = app_user_id())
4) runtime-role grants
5) touch_updated_at trigger on recommendations

Design sources:
docs/architecture/module-contracts.md (§M.9 Recommendations),
docs/requirements/requirements-analysis.md,
docs/architecture/domain-events.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0008_phase8_recommendations"
down_revision = "0007_phase7_growth"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"
FN_TOUCH_UPDATED_AT = "touch_updated_at"

T_RECOMMENDATIONS = "recommendations"
T_RECOMMENDATION_FEEDBACK = "recommendation_feedback"

PHASE8_TABLES = [
    T_RECOMMENDATIONS,
    T_RECOMMENDATION_FEEDBACK,
]

RLS_POLICIES: list[tuple[str, str]] = [
    (T_RECOMMENDATIONS, "recommendations_all_access"),
    (T_RECOMMENDATION_FEEDBACK, "recommendation_feedback_all_access"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) recommendations — persistent personalized learning actions
    op.create_table(
        T_RECOMMENDATIONS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="0.50"),
        sa.Column("priority_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_target", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("algorithm_version", sa.String(32), nullable=False, server_default="rec-1.0"),
        sa.Column("source_growth_event_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "priority_score >= 0.0 AND priority_score <= 1.0",
            name="chk_recommendations_priority_score",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'VIEWED', 'STARTED', 'COMPLETED', 'DISMISSED', 'EXPIRED')",
            name="chk_recommendations_status",
        ),
        comment="Personalized learning recommendations. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_recommendations_project_owner", T_RECOMMENDATIONS, ["project_id", "owner_id"])
    op.create_index("ix_recommendations_concept_id", T_RECOMMENDATIONS, ["concept_id"])
    op.create_index("ix_recommendations_owner_id", T_RECOMMENDATIONS, ["owner_id"])
    op.create_index("ix_recommendations_source_growth_event", T_RECOMMENDATIONS, ["source_growth_event_id"])
    op.create_index(
        "ix_recommendations_project_status",
        T_RECOMMENDATIONS,
        ["project_id", "status", "created_at"],
    )
    op.create_index(
        "ix_recommendations_project_concept_status",
        T_RECOMMENDATIONS,
        ["project_id", "concept_id", "status"],
    )

    # 2) recommendation_feedback — audit history of learner interaction on recommendations
    op.create_table(
        T_RECOMMENDATION_FEEDBACK,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id", ondelete="CASCADE"),
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
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "action IN ('viewed', 'started', 'completed', 'dismissed')",
            name="chk_recommendation_feedback_action",
        ),
        comment="Learner feedback on recommendations. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_rec_feedback_rec_id", T_RECOMMENDATION_FEEDBACK, ["recommendation_id"])
    op.create_index("ix_rec_feedback_project_owner", T_RECOMMENDATION_FEEDBACK, ["project_id", "owner_id"])
    op.create_index("ix_rec_feedback_owner_id", T_RECOMMENDATION_FEEDBACK, ["owner_id"])

    # 3) Enable RLS on all Phase 8 tables
    for tbl in PHASE8_TABLES:
        conn.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"))
        conn.execute(text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;"))

    # 4) Create RLS policies
    for tbl, policy_name in RLS_POLICIES:
        conn.execute(
            text(
                f"""
                CREATE POLICY {policy_name} ON {tbl}
                FOR ALL
                TO {ROLE_RUNTIME}
                USING (owner_id = {FN_APP_USER}())
                WITH CHECK (owner_id = {FN_APP_USER}());
                """
            )
        )

    # 5) Grant CRUD permissions to runtime role
    for tbl in PHASE8_TABLES:
        conn.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO {ROLE_RUNTIME};"
            )
        )

    # 6) touch_updated_at trigger
    conn.execute(
        text(
            f"""
            CREATE TRIGGER trg_{T_RECOMMENDATIONS}_touch_updated_at
            BEFORE UPDATE ON {T_RECOMMENDATIONS}
            FOR EACH ROW
            EXECUTE FUNCTION {FN_TOUCH_UPDATED_AT}();
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop triggers
    conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{T_RECOMMENDATIONS}_touch_updated_at ON {T_RECOMMENDATIONS};"))

    # Drop policies
    for tbl, policy_name in RLS_POLICIES:
        conn.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {tbl};"))

    # Drop tables in reverse dependency order
    op.drop_table(T_RECOMMENDATION_FEEDBACK)
    op.drop_table(T_RECOMMENDATIONS)
