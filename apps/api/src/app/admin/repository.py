"""Admin repository for audit logs, job execution telemetry, and platform queries (Phase 10).

Executes administrative read models and audit persistence.
Adheres strictly to module boundaries (no cross-module model imports).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.admin.models import AdminAuditLog, JobExecutionRecord
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession


class AdminRepository:
    """Async database repository for administrative telemetry and audit tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_audit_log(self, log: AdminAuditLog) -> AdminAuditLog:
        """Persist an administrative audit log entry."""
        self._session.add(log)
        await self._session.flush()
        return log

    async def list_audit_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
    ) -> tuple[list[AdminAuditLog], int]:
        """List audit logs with bounded pagination."""
        q = select(AdminAuditLog)
        count_q = select(func.count(AdminAuditLog.id))

        if actor_id is not None:
            q = q.where(AdminAuditLog.actor_user_id == actor_id)
            count_q = count_q.where(AdminAuditLog.actor_user_id == actor_id)
        if action is not None:
            q = q.where(AdminAuditLog.action == action)
            count_q = count_q.where(AdminAuditLog.action == action)

        total_res = await self._session.execute(count_q)
        total = total_res.scalar_one()

        q = (
            q.order_by(desc(AdminAuditLog.occurred_at), desc(AdminAuditLog.id))
            .offset(offset)
            .limit(limit)
        )
        res = await self._session.execute(q)
        return list(res.scalars().all()), total

    async def save_job_execution(self, record: JobExecutionRecord) -> JobExecutionRecord:
        """Persist a background job execution telemetry entry."""
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_job_executions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[JobExecutionRecord], int]:
        """List job execution telemetry with bounded pagination."""
        q = select(JobExecutionRecord)
        count_q = select(func.count(JobExecutionRecord.id))

        if status is not None:
            q = q.where(JobExecutionRecord.status == status)
            count_q = count_q.where(JobExecutionRecord.status == status)

        total_res = await self._session.execute(count_q)
        total = total_res.scalar_one()

        q = (
            q.order_by(desc(JobExecutionRecord.created_at), desc(JobExecutionRecord.id))
            .offset(offset)
            .limit(limit)
        )
        res = await self._session.execute(q)
        return list(res.scalars().all()), total

    async def get_job_counts(self) -> dict[str, int]:
        """Aggregate background job execution counts."""
        stmt = select(
            JobExecutionRecord.status,
            func.count(JobExecutionRecord.id),
        ).group_by(JobExecutionRecord.status)
        res = await self._session.execute(stmt)
        counts: dict[str, int] = {
            "total": 0,
            "succeeded": 0,
            "failed": 0,
            "retrying": 0,
            "pending": 0,
            "running": 0,
        }
        for status_val, c in res.all():
            counts["total"] += c
            key = str(status_val).lower()
            if key in counts:
                counts[key] = c
        return counts

    # --- Platform Read-Model SQL Aggregations (Boundary-Safe via SQL) ---

    async def get_user_stats(self) -> dict[str, int]:
        """Count total, active, and admin users."""
        stmt = text("""
            SELECT
                count(*) as total,
                count(*) FILTER (WHERE status = 'active') as active,
                count(*) FILTER (WHERE role = 'admin') as admins
            FROM users;
            """)
        res = await self._session.execute(stmt)
        row = res.mappings().one()
        return {
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
            "admins": int(row["admins"] or 0),
        }

    async def get_space_count(self) -> int:
        """Count total spaces."""
        res = await self._session.execute(text("SELECT count(*) FROM spaces;"))
        return int(res.scalar_one() or 0)

    async def get_project_count(self) -> int:
        """Count total projects."""
        res = await self._session.execute(text("SELECT count(*) FROM projects;"))
        return int(res.scalar_one() or 0)

    async def get_material_stats(self) -> dict[str, int]:
        """Count total materials by status."""
        stmt = text("""
            SELECT
                count(*) as total,
                count(*) FILTER (WHERE status IN ('ready', 'completed')) as ready,
                count(*) FILTER (WHERE status = 'processing') as processing,
                count(*) FILTER (WHERE status = 'upload_pending') as upload_pending,
                count(*) FILTER (WHERE status = 'failed') as failed
            FROM materials;
            """)
        res = await self._session.execute(stmt)
        row = res.mappings().one()
        return {
            "total": int(row["total"] or 0),
            "ready": int(row["ready"] or 0),
            "processing": int(row["processing"] or 0),
            "upload_pending": int(row["upload_pending"] or 0),
            "failed": int(row["failed"] or 0),
        }

    async def list_recent_material_failures(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recently failed material records."""
        stmt = text("""
            SELECT id, project_id, title, status, size_bytes, failure_reason, created_at
            FROM materials
            WHERE status = 'failed'
            ORDER BY created_at DESC
            LIMIT :limit;
            """)
        res = await self._session.execute(stmt, {"limit": limit})
        return [dict(row) for row in res.mappings().all()]

    async def list_users_paginated(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        role: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query users table with search and pagination (safe fields only)."""
        base_where = "WHERE 1=1"
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if search:
            base_where += " AND (lower(email) LIKE :search OR lower(display_name) LIKE :search)"
            params["search"] = f"%{search.strip().lower()}%"
        if role:
            base_where += " AND role = :role"
            params["role"] = role

        count_sql = text(f"SELECT count(*) FROM users {base_where};")
        total_res = await self._session.execute(count_sql, params)
        total = int(total_res.scalar_one() or 0)

        data_sql = text(f"""
            SELECT id, email, display_name, role, status, created_at
            FROM users
            {base_where}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset;
            """)
        res = await self._session.execute(data_sql, params)
        return [dict(row) for row in res.mappings().all()], total

    async def get_user_detail(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch user profile with related counts."""
        stmt = text("""
            SELECT
                u.id, u.email, u.display_name, u.role, u.status, u.created_at,
                (SELECT count(*) FROM spaces s WHERE s.owner_id = u.id) as spaces_count,
                (SELECT count(*) FROM projects p WHERE p.owner_id = u.id) as projects_count,
                (SELECT count(*) FROM analytics_events e WHERE e.user_id = u.id) as study_events_count,
                (SELECT max(occurred_at) FROM analytics_events e WHERE e.user_id = u.id) as last_activity_at
            FROM users u
            WHERE u.id = :user_id;
            """)
        res = await self._session.execute(stmt, {"user_id": user_id})
        row = res.mappings().one_or_none()
        return dict(row) if row else None

    async def list_projects_paginated(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query projects table with pagination and related counts."""
        count_sql = text("SELECT count(*) FROM projects;")
        total_res = await self._session.execute(count_sql)
        total = int(total_res.scalar_one() or 0)

        data_sql = text("""
            SELECT
                p.id, p.space_id, p.owner_id, p.name, p.created_at,
                (SELECT count(*) FROM materials m WHERE m.project_id = p.id) as materials_count,
                (SELECT count(*) FROM analytics_events e WHERE e.project_id = p.id) as activity_count
            FROM projects p
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT :limit OFFSET :offset;
            """)
        res = await self._session.execute(data_sql, {"limit": limit, "offset": offset})
        return [dict(row) for row in res.mappings().all()], total

    async def get_project_detail(self, project_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch project detail with domain counts."""
        stmt = text("""
            SELECT
                p.id, p.space_id, p.owner_id, p.name, p.created_at,
                (SELECT count(*) FROM materials m WHERE m.project_id = p.id) as materials_count,
                (SELECT count(*) FROM conversations c WHERE c.project_id = p.id) as conversations_count,
                (SELECT count(*) FROM quizzes q WHERE q.project_id = p.id) as quizzes_count,
                (SELECT count(*) FROM concept_mastery cm WHERE cm.project_id = p.id AND cm.mastery_probability >= 0.85) as mastered_concepts,
                (SELECT count(*) FROM recommendations r WHERE r.project_id = p.id) as recommendations_count
            FROM projects p
            WHERE p.id = :project_id;
            """)
        res = await self._session.execute(stmt, {"project_id": project_id})
        row = res.mappings().one_or_none()
        return dict(row) if row else None
