"""Phase 5 — Adaptive Assessment & Open-Ended Assessment schema.

Review order:
1) tables: quizzes → questions → question_options → question_attempts → quiz_evidence
2) indexes for adaptive selection and project-scoped queries
3) RLS policies (permissive FOR ALL to studycompanion_runtime USING owner_id = app_user_id())
4) runtime-role grants

Design sources:
docs/architecture/module-contracts.md (§6 Assessment),
docs/requirements/requirements-analysis.md (FR-50..55),
docs/architecture/domain-events.md (§2.4 Assessment events).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "0005_phase5_assessment"
down_revision = "0004_phase4_tutor"
branch_labels = None
depends_on = None

ROLE_RUNTIME = "studycompanion_runtime"
FN_APP_USER = "app_user_id"
FN_TOUCH_UPDATED_AT = "touch_updated_at"

T_QUIZZES = "quizzes"
T_QUESTIONS = "questions"
T_QUESTION_OPTIONS = "question_options"
T_QUESTION_ATTEMPTS = "question_attempts"
T_QUIZ_EVIDENCE = "quiz_evidence"

PHASE5_TABLES = [
    T_QUIZZES,
    T_QUESTIONS,
    T_QUESTION_OPTIONS,
    T_QUESTION_ATTEMPTS,
    T_QUIZ_EVIDENCE,
]

RLS_POLICIES: list[tuple[str, str]] = [
    (T_QUIZZES, "quizzes_all_access"),
    (T_QUESTIONS, "questions_all_access"),
    (T_QUESTION_OPTIONS, "question_options_all_access"),
    (T_QUESTION_ATTEMPTS, "question_attempts_all_access"),
    (T_QUIZ_EVIDENCE, "quiz_evidence_all_access"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1) quizzes — the quiz session container
    op.create_table(
        T_QUIZZES,
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
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="created",
        ),
        sa.Column("mode", sa.String(32), nullable=False, server_default="adaptive"),
        sa.Column("target_question_count", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("answered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_score", sa.Float(), nullable=True),
        # concept_ids the user wants to focus on (nullable = all concepts)
        sa.Column("concept_ids", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
            "status IN ('created', 'active', 'completed', 'abandoned')",
            name="ck_quizzes_status",
        ),
        sa.CheckConstraint(
            "mode IN ('adaptive', 'concept_focus', 'difficulty_focus')",
            name="ck_quizzes_mode",
        ),
        comment="Quiz sessions owned by Assessment. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_quizzes_project_owner", T_QUIZZES, ["project_id", "owner_id"])
    op.create_index("ix_quizzes_owner_id", T_QUIZZES, ["owner_id"])
    op.create_index("ix_quizzes_status", T_QUIZZES, ["status"])

    # 2) questions — RAG-grounded question bank
    op.create_table(
        T_QUESTIONS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quiz_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
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
        # concept_id nullable — Phase 6 will connect once concept graph exists
        sa.Column("concept_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        # MCQ: correct option id (A/B/C/D) — NEVER exposed in QuestionDto
        sa.Column("correct_option", sa.String(4), nullable=True),
        # Open-ended: reference answer — NEVER exposed in QuestionDto
        sa.Column("reference_answer", sa.Text(), nullable=True),
        # Open-ended: rubric as JSON array of {criterion, weight}
        sa.Column("rubric", sa.JSON(), nullable=True),
        # Provenance: chunk ids that grounded this question
        sa.Column("source_chunk_ids", sa.JSON(), nullable=False),
        # AI generation metadata
        sa.Column("generation_model", sa.Text(), nullable=True),
        sa.Column("ai_request_id", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "question_type IN ('mcq', 'open_ended')",
            name="ck_questions_type",
        ),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')",
            name="ck_questions_difficulty",
        ),
        comment="RAG-grounded questions. Answer keys never exposed via API. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_questions_quiz_id", T_QUESTIONS, ["quiz_id"])
    op.create_index("ix_questions_project_owner", T_QUESTIONS, ["project_id", "owner_id"])
    op.create_index("ix_questions_concept_id", T_QUESTIONS, ["concept_id"])
    op.create_index("ix_questions_difficulty", T_QUESTIONS, ["difficulty"])

    # 3) question_options — MCQ options (1:N per question)
    op.create_table(
        T_QUESTION_OPTIONS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "question_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # option_id = A, B, C, D
        sa.Column("option_id", sa.String(4), nullable=False),
        sa.Column("option_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("question_id", "option_id", name="uq_question_options_question_option"),
        comment="MCQ answer options. RLS: owner_id = app_user_id()",
    )
    op.create_index("ix_question_options_question_id", T_QUESTION_OPTIONS, ["question_id"])
    op.create_index("ix_question_options_owner_id", T_QUESTION_OPTIONS, ["owner_id"])

    # 4) question_attempts — immutable answer records (never overwrite)
    op.create_table(
        T_QUESTION_ATTEMPTS,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quiz_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
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
        # The learner's raw answer (MCQ: option id; open-ended: free text)
        sa.Column("learner_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        # deterministic | ai | pending_review
        sa.Column("grading_method", sa.String(32), nullable=False, server_default="deterministic"),
        sa.Column("grading_model", sa.Text(), nullable=True),
        sa.Column("ai_request_id", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        # AI grading output detail (JSON: criteria scores, confidence)
        sa.Column("grading_detail", sa.JSON(), nullable=True),
        # Idempotency: unique per (quiz, question)
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "grading_method IN ('deterministic', 'ai', 'pending_review')",
            name="ck_question_attempts_grading_method",
        ),
        comment="Immutable learner answer records. RLS: owner_id = app_user_id()",
    )
    # Unique constraint: one attempt per (quiz, question) — enforces immutability
    op.create_index(
        "uq_question_attempts_quiz_question",
        T_QUESTION_ATTEMPTS,
        ["quiz_id", "question_id"],
        unique=True,
    )
    op.create_index("ix_question_attempts_quiz_id", T_QUESTION_ATTEMPTS, ["quiz_id"])
    op.create_index("ix_question_attempts_question_id", T_QUESTION_ATTEMPTS, ["question_id"])
    op.create_index("ix_question_attempts_project_owner", T_QUESTION_ATTEMPTS, ["project_id", "owner_id"])
    op.create_index(
        "uq_question_attempts_idempotency",
        T_QUESTION_ATTEMPTS,
        ["quiz_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # 5) quiz_evidence — structured learning evidence for Phase 6 Mastery
    op.create_table(
        T_QUIZ_EVIDENCE,
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("question_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "quiz_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
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
        # concept_id nullable — Phase 6 backfills via question concept_id
        sa.Column("concept_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),  # correct | incorrect | partial
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("question_type", sa.String(32), nullable=False),
        sa.Column("grading_method", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="assessment"),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "result IN ('correct', 'incorrect', 'partial')",
            name="ck_quiz_evidence_result",
        ),
        comment="Structured learning evidence for Phase 6 Mastery. RLS: owner_id = app_user_id()",
    )
    # Unique: one evidence row per attempt (idempotent evidence emission)
    op.create_index(
        "uq_quiz_evidence_attempt",
        T_QUIZ_EVIDENCE,
        ["attempt_id"],
        unique=True,
    )
    op.create_index("ix_quiz_evidence_project_owner", T_QUIZ_EVIDENCE, ["project_id", "owner_id"])
    op.create_index("ix_quiz_evidence_concept_id", T_QUIZ_EVIDENCE, ["concept_id"])
    op.create_index("ix_quiz_evidence_quiz_id", T_QUIZ_EVIDENCE, ["quiz_id"])

    # 6) touch_updated_at triggers for quizzes
    for tbl in [T_QUIZZES]:
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

    # 7) Enable RLS & create policies
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

    # 8) Grants to runtime role
    for tbl in PHASE5_TABLES:
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
    for tbl in [T_QUIZZES]:
        conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{tbl}_touch_updated_at ON {tbl};"))

    # Drop tables in reverse dependency order
    for tbl in reversed(PHASE5_TABLES):
        op.drop_table(tbl)
