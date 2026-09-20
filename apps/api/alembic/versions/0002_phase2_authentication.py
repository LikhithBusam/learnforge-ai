"""Phase 2 — authentication support (ADR-0018/0023).

Additive only (no history rewrite of 0001):
1. ``users.display_name`` — registration profile field (PRD identity).
2. ``refresh_sessions.family_id`` — rotation family for theft detection:
   reuse of any rotated token revokes every member of the family
   (family_id is copied from the parent at rotation).
3. ``auth_session_lookup(token_hash, now)`` / ``auth_user_credentials(email)``
   SECURITY DEFINER — the ONLY pre-authentication reads (RLS chicken-and-egg:
   no user context exists before login/refresh, and the ``users`` policy is
   fail-closed by design). Minimal surfaces: the session tuple and the
   credential tuple respectively — not general-purpose table reads. The
   runtime role gets EXECUTE; all post-authentication reads remain under RLS.
   ``auth_session_lookup`` returns REVOKED sessions too (unexpired): reuse of
   a rotated token must be detectable so the service can revoke the family.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0002_phase2_authentication"
down_revision = "0001_phase1_identity_workspace"
branch_labels = None
depends_on = None

T_USERS = "users"
T_SESSIONS = "refresh_sessions"
ROLE_RUNTIME = "studycompanion_runtime"
FN_AUTH_LOOKUP = "auth_session_lookup"
FN_USER_CREDENTIALS = "auth_user_credentials"


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        T_USERS,
        sa.Column("display_name", sa.Text(), nullable=True),
    )

    op.add_column(
        T_SESSIONS,
        sa.Column("family_id", sa.Uuid(), nullable=True),
    )
    # Backfill existing rows: each session starts its own family.
    conn.execute(text(f"UPDATE {T_SESSIONS} SET family_id = id WHERE family_id IS NULL"))
    op.alter_column(T_SESSIONS, "family_id", nullable=False, existing_type=sa.Uuid())
    op.create_index("ix_refresh_sessions_family_id", T_SESSIONS, ["family_id"])

    # SECURITY DEFINER helper — runs with the function owner's rights (the
    # migration role) so the runtime role can perform the pre-auth lookup.
    conn.execute(text(f"""
    CREATE OR REPLACE FUNCTION {FN_AUTH_LOOKUP}(p_token_hash text, p_now timestamptz)
    RETURNS TABLE (
        session_id uuid,
        out_user_id uuid,
        family_id uuid,
        expires_at timestamptz,
        revoked_at timestamptz
    )
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
        SELECT s.id, s.user_id, s.family_id, s.expires_at, s.revoked_at
        FROM {T_SESSIONS} s
        WHERE s.token_hash = p_token_hash
          AND s.expires_at > p_now;
    $fn$;
            """))
    conn.execute(text(f"REVOKE ALL ON FUNCTION {FN_AUTH_LOOKUP}(text, timestamptz) FROM PUBLIC"))
    conn.execute(
        text(f"GRANT EXECUTE ON FUNCTION {FN_AUTH_LOOKUP}(text, timestamptz) TO {ROLE_RUNTIME}")
    )

    # Credential lookup for login: the caller has NOT authenticated yet, so
    # no RLS context exists. Returns the minimal credential tuple for an
    # ACTIVE account only; missing vs disabled are indistinguishable (NULL).
    conn.execute(text(f"""
    CREATE OR REPLACE FUNCTION {FN_USER_CREDENTIALS}(p_email text)
    RETURNS TABLE (
        user_id uuid,
        email_out text,
        display_name_out text,
        password_hash_out text,
        role_out text
    )
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $fn$
        SELECT u.id, u.email, u.display_name, u.password_hash, u.role
        FROM {T_USERS} u
        WHERE lower(u.email) = lower(p_email)
          AND u.status = 'active';
    $fn$;
            """))
    conn.execute(text(f"REVOKE ALL ON FUNCTION {FN_USER_CREDENTIALS}(text) FROM PUBLIC"))
    conn.execute(text(f"GRANT EXECUTE ON FUNCTION {FN_USER_CREDENTIALS}(text) TO {ROLE_RUNTIME}"))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text(f"DROP FUNCTION IF EXISTS {FN_AUTH_LOOKUP}(text, timestamptz)"))
    conn.execute(text(f"DROP FUNCTION IF EXISTS {FN_USER_CREDENTIALS}(text)"))
    op.drop_index("ix_refresh_sessions_family_id", table_name=T_SESSIONS)
    op.drop_column(T_SESSIONS, "family_id")
    op.drop_column(T_USERS, "display_name")
