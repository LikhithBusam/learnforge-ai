"""Phase 9 — Analytics & Learner Progress schema.

Review order:
1) tables: analytics_events → project_daily_metrics
2) indexes for fast time-series queries and unique daily rollup constraints
3) RLS policies (permissive FOR ALL to studycompanion_runtime USING user_id/owner_id = app_user_id())
4) runtime-role grants

Design sources:
docs/architecture/module-contracts.md (§M.10 Analytics),
docs/requirements/requirements-analysis.md,
docs/architecture/domain-events.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0009_phase9_analytics"
down_revision = "0008_phase8_recommendations"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"

T_ANALYTICS_EVENTS = "analytics_events"
T_PROJECT_DAILY_METRICS = "project_daily_metrics"

PHASE9_TABLES = [
    T_ANALYTICS_EVENTS,
    T_PROJECT_DAILY_METRICS,
]

RLS_POLICIES: list[tuple[str, str, str]] = [
    (T_ANALYTICS_EVENTS, "analytics_events_all_access", "user_id"),
    (T_PROJECT_DAILY_METRICS, "project_daily_metrics_all_access", "owner_id"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) analytics_events — immutable timestamped learning event stream
    op.create_table(
        T_ANALYTICS_EVENTS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        comment="Immutable analytics events. RLS: user_id = app_user_id()",
    )
    op.create_index("ix_analytics_events_event_type", T_ANALYTICS_EVENTS, ["event_type"])
    op.create_index("ix_analytics_events_user_id", T_ANALYTICS_EVENTS, ["user_id"])
    op.create_index("ix_analytics_events_project_id", T_ANALYTICS_EVENTS, ["project_id"])
    op.create_index(
        "ix_analytics_events_project_occurred",
        T_ANALYTICS_EVENTS,
        ["project_id", "occurred_at"],
    )
    op.create_index(
        "ix_analytics_events_project_type",
        T_ANALYTICS_EVENTS,
        ["project_id", "event_type"],
    )
    op.create_index(
        "ix_analytics_events_user_occurred",
        T_ANALYTICS_EVENTS,
        ["user_id", "occurred_at"],
    )

    # 2) project_daily_metrics — precomputed daily metric rollups
    op.create_table(
        T_PROJECT_DAILY_METRICS,
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
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("metric_category", sa.String(64), nullable=False),
        sa.Column(
            "metrics_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "project_id",
            "date",
            "metric_category",
            name="uq_project_daily_metrics_proj_date_cat",
        ),
        comment="Daily project metric rollups. RLS: owner_id = app_user_id()",
    )
    op.create_index(
        "ix_project_daily_metrics_proj_date",
        T_PROJECT_DAILY_METRICS,
        ["project_id", "date"],
    )
    op.create_index("ix_project_daily_metrics_owner_id", T_PROJECT_DAILY_METRICS, ["owner_id"])

    # 3) Enable RLS on all Phase 9 tables
    for tbl in PHASE9_TABLES:
        conn.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"))
        conn.execute(text(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;"))

    # 4) Create RLS policies
    for tbl, policy_name, user_col in RLS_POLICIES:
        conn.execute(
            text(
                f"""
                CREATE POLICY {policy_name} ON {tbl}
                FOR ALL
                TO {ROLE_RUNTIME}
                USING ({user_col} = {FN_APP_USER}())
                WITH CHECK ({user_col} = {FN_APP_USER}());
                """
            )
        )

    # 5) Grant CRUD permissions to runtime role
    for tbl in PHASE9_TABLES:
        conn.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO {ROLE_RUNTIME};"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop policies
    for tbl, policy_name, _ in RLS_POLICIES:
        conn.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {tbl};"))

    # Drop tables in reverse dependency order
    op.drop_table(T_PROJECT_DAILY_METRICS)
    op.drop_table(T_ANALYTICS_EVENTS)
