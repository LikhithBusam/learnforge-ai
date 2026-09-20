"""Phase 10 — Admin Dashboard & System Observability schema.

Review order:
1) tables: admin_audit_logs → job_executions
2) indexes for fast audit search and job status aggregation
3) RLS policies and runtime-role grants

Design sources:
docs/architecture/module-contracts.md (§M.11 Admin),
docs/requirements/requirements-analysis.md.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0010_phase10_admin_observability"
down_revision = "0009_phase9_analytics"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"

T_ADMIN_AUDIT_LOGS = "admin_audit_logs"
T_JOB_EXECUTIONS = "job_executions"

PHASE10_TABLES = [
    T_ADMIN_AUDIT_LOGS,
    T_JOB_EXECUTIONS,
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) admin_audit_logs — immutable audit log of administrative actions
    op.create_table(
        T_ADMIN_AUDIT_LOGS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_role", sa.String(32), nullable=False, server_default="admin"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column(
            "metadata_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        comment="Administrative audit logs. RLS: actor_user_id = app_user_id()",
    )
    op.create_index("ix_admin_audit_actor_user_id", T_ADMIN_AUDIT_LOGS, ["actor_user_id"])
    op.create_index("ix_admin_audit_action", T_ADMIN_AUDIT_LOGS, ["action"])
    op.create_index("ix_admin_audit_occurred_at", T_ADMIN_AUDIT_LOGS, ["occurred_at"])
    op.create_index("ix_admin_audit_correlation_id", T_ADMIN_AUDIT_LOGS, ["correlation_id"])
    op.create_index(
        "ix_admin_audit_actor_occurred",
        T_ADMIN_AUDIT_LOGS,
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_admin_audit_action_occurred",
        T_ADMIN_AUDIT_LOGS,
        ["action", "occurred_at"],
    )

    # 2) job_executions — background job execution telemetry
    op.create_table(
        T_JOB_EXECUTIONS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_name", sa.String(128), nullable=False),
        sa.Column("queue", sa.String(64), nullable=False, server_default="default"),
        sa.Column("status", sa.String(32), nullable=False, server_default="SUCCEEDED"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        comment="Job execution telemetry and history.",
    )
    op.create_index("ix_job_executions_task_name", T_JOB_EXECUTIONS, ["task_name"])
    op.create_index("ix_job_executions_status", T_JOB_EXECUTIONS, ["status"])
    op.create_index("ix_job_executions_correlation_id", T_JOB_EXECUTIONS, ["correlation_id"])
    op.create_index("ix_job_executions_created_at", T_JOB_EXECUTIONS, ["created_at"])
    op.create_index(
        "ix_job_executions_task_created",
        T_JOB_EXECUTIONS,
        ["task_name", "created_at"],
    )
    op.create_index(
        "ix_job_executions_status_created",
        T_JOB_EXECUTIONS,
        ["status", "created_at"],
    )

    # 3) Enable RLS on admin audit logs
    conn.execute(text(f"ALTER TABLE {T_ADMIN_AUDIT_LOGS} ENABLE ROW LEVEL SECURITY;"))
    conn.execute(text(f"ALTER TABLE {T_ADMIN_AUDIT_LOGS} FORCE ROW LEVEL SECURITY;"))

    conn.execute(
        text(
            f"""
            CREATE POLICY admin_audit_logs_all_access ON {T_ADMIN_AUDIT_LOGS}
            FOR ALL
            TO {ROLE_RUNTIME}
            USING (actor_user_id = {FN_APP_USER}())
            WITH CHECK (actor_user_id = {FN_APP_USER}());
            """
        )
    )

    # 4) Grant CRUD permissions to runtime role
    for tbl in PHASE10_TABLES:
        conn.execute(
            text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO {ROLE_RUNTIME};"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop policies
    conn.execute(text(f"DROP POLICY IF EXISTS admin_audit_logs_all_access ON {T_ADMIN_AUDIT_LOGS};"))

    # Drop tables in reverse dependency order
    op.drop_table(T_JOB_EXECUTIONS)
    op.drop_table(T_ADMIN_AUDIT_LOGS)
