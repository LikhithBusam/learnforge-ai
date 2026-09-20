"""Application configuration.

12-factor: everything from environment variables, validated at startup.
The application refuses to boot on missing/malformed configuration
(ADR-0012 / security-baseline §1). Development defaults are documented in
`.env.example`; production values are injected by the platform secrets facility.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["development", "test", "staging", "production"]


def _project_root() -> str:
    """Anchor env-file lookup to the repo root so CLI tools that run from
    subdirectories (e.g. `apps/api` for Alembic) resolve the same env files
    as the application. First marker found walking upward wins."""
    from pathlib import Path

    current = Path(__file__).resolve().parent
    for _ in range(8):
        if (current / "pyproject.toml").exists() or (current / ".env.example").exists():
            return str(current)
        if current.parent == current:
            break
        current = current.parent
    return str(Path.cwd())


def _mask(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(
            str(Path(_project_root()) / name) for name in (".env.test", ".env.development", ".env")
        ),  # noqa: UP037 - runtime value
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Environment / core ---
    APP_ENV: Env = "development"
    APP_VERSION: str = "dev"
    LOG_LEVEL: str = "INFO"
    API_BASE_URL: str = "http://localhost:8000"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"

    # --- Database (PostgreSQL 16 + pgvector; ADR-0013) ---
    DATABASE_URL: str = ""
    # Runtime role URL (Phase 1, Part 8): MUST point at a non-superuser,
    # non-BYPASSRLS role. Refuses to equal DATABASE_URL (owner/migration role).
    DATABASE_RUNTIME_URL: str = ""
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_STATEMENT_TIMEOUT_MS: int = 10000

    # --- Redis (ADR-0014 — never a system of record) ---
    REDIS_URL: str = ""

    # --- Object storage (ADR-0016) ---
    # STORAGE_PROVIDER selects the implementation behind the StorageProvider
    # abstraction: "supabase" (cloud-first), "minio" (local compose), or ""
    # (auto: in-memory for dev/test without credentials, minio otherwise).
    STORAGE_PROVIDER: str = ""
    # Supabase (ADR-0022): project URL + server-side secret key (service_role).
    # The secret key is NEVER included in safe_summary()/logs/health output.
    SUPABASE_URL: str = ""
    SUPABASE_SECRET_KEY: str = ""
    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_PUBLIC_ENDPOINT: str = ""
    STORAGE_BUCKET: str = "studycompanion-dev"
    STORAGE_ACCESS_KEY_ID: str = ""
    STORAGE_SECRET_ACCESS_KEY: str = ""
    STORAGE_REGION: str = "us-east-1"
    STORAGE_PRESIGN_TTL_SECONDS: int = 900
    MAX_UPLOAD_BYTES: int = 52428800
    MAX_PDF_PAGES: int = 500

    # --- Auth (ADR-0018 / ADR-0023) ---
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_ALGORITHM: str = "RS256"
    JWT_ISSUER: str = "study-companion"
    JWT_AUDIENCE: str = "study-companion-api"
    JWT_ACCESS_TTL_SECONDS: int = 900
    REFRESH_TTL_DAYS: int = 30
    # Refresh-token cookie (ADR-0018: HttpOnly; Secure; SameSite=Strict).
    REFRESH_COOKIE_SECURE: bool = False  # dev=False; production deployment sets True
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_KIB: int = 65536
    # Admin bootstrap (Part 16): one-time, env-gated CLI only — never an API.
    ADMIN_BOOTSTRAP_EMAIL: str = ""
    ADMIN_BOOTSTRAP_TOKEN: str = ""

    # --- AI provider roles (ADR-0015; AI_PROVIDER_REGISTRY=stub requires no keys) ---
    AI_PROVIDER: str = "stub"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_PROVIDER_REGISTRY: str = "stub"
    AI_GENERATION_PROVIDER: str = "stub"
    AI_GENERATION_MODEL: str = "stub-generation"
    AI_GENERATION_API_KEY_REF: str | None = None
    AI_GENERATION_TIMEOUT_SECONDS: int = 30
    AI_GENERATION_MAX_TOKENS: int = 1024
    AI_GENERATION_TEMPERATURE: float = 0.0
    AI_GENERATION_FALLBACK_PROVIDER: str = "stub"
    AI_GENERATION_FALLBACK_MODEL: str = "stub-generation"
    AI_GENERATION_FALLBACK_API_KEY_REF: str | None = None
    AI_STRUCTURED_PROVIDER: str = "stub"
    AI_STRUCTURED_MODEL: str = "stub-structured"
    AI_STRUCTURED_API_KEY_REF: str | None = None
    AI_STRUCTURED_TIMEOUT_SECONDS: int = 60
    AI_STRUCTURED_TEMPERATURE: float = 0.0
    AI_EMBEDDING_PROVIDER: str = "stub"
    AI_EMBEDDING_MODEL: str = "stub-embedding"
    AI_EMBEDDING_API_KEY_REF: str | None = None
    AI_EMBEDDING_DIMENSIONS: int = 1536
    AI_EMBEDDING_BATCH_SIZE: int = 128
    AI_RERANKER_PROVIDER: str = "stub"
    AI_RERANKER_MODEL: str = "stub-reranker"
    AI_RERANKER_API_KEY_REF: str | None = None
    AI_EVALUATION_PROVIDER: str = "stub"
    AI_EVALUATION_MODEL: str = "stub-evaluation"
    AI_EVALUATION_API_KEY_REF: str | None = None
    AI_VISION_PROVIDER: str = "stub"
    AI_VISION_MODEL: str = "stub-vision"
    AI_VISION_API_KEY_REF: str | None = None
    AI_USER_DAILY_TOKEN_BUDGET: int = 1_000_000
    AI_PRICE_TABLE_REF: str | None = None

    # --- Retrieval policy (Phase 4 hybrid RAG) ---
    RETRIEVAL_TOP_K: int = 30
    RETRIEVAL_VECTOR_TOP_K: int = 20
    RETRIEVAL_LEXICAL_TOP_K: int = 20
    RETRIEVAL_FUSION_TOP_K: int = 20
    RETRIEVAL_RERANK_TO: int = 6
    RETRIEVAL_FINAL_CONTEXT_TOP_K: int = 5
    RETRIEVAL_RRF_K: int = 60
    RETRIEVAL_SUFFICIENCY_TAU: float | None = 0.50
    RETRIEVAL_MIN_SUPPORTING_CHUNKS: int = 1
    CHUNK_TARGET_TOKENS: int = 500
    CHUNK_OVERLAP_RATIO: float = 0.15
    CONTEXT_TOKEN_BUDGET: int = 6000
    TUTOR_MAX_HISTORY_MESSAGES: int = 6

    # --- Assessment policy (Phase 5) ---
    ASSESSMENT_DEFAULT_QUESTION_COUNT: int = 5
    ASSESSMENT_MAX_QUESTION_COUNT: int = 20
    ASSESSMENT_GRADING_CONFIDENCE_THRESHOLD: float = 0.70

    # --- Mastery policy (Phase 6 BKT) ---
    MASTERY_P_INIT: float = 0.20
    MASTERY_P_LEARN: float = 0.10
    MASTERY_P_GUESS: float = 0.20
    MASTERY_P_SLIP: float = 0.10
    MASTERY_PARTIAL_CREDIT_WEIGHT: float = 0.50
    MASTERY_EASY_WEIGHT: float = 0.80
    MASTERY_MEDIUM_WEIGHT: float = 1.00
    MASTERY_HARD_WEIGHT: float = 1.20
    MASTERY_CONFIDENCE_K: float = 5.0
    MASTERY_ALGORITHM_VERSION: str = "bkt-1.0"

    # --- Growth policy (Phase 7) ---
    GROWTH_MIN_OBSERVATIONS: int = 2
    GROWTH_STABILITY_DELTA: float = 0.05
    GROWTH_SIGNIFICANT_DELTA: float = 0.10
    GROWTH_SHORT_TERM_WINDOW: int = 3
    GROWTH_LONG_TERM_WINDOW: int = 10
    GROWTH_ATTENTION_THRESHOLD: float = 0.50
    GROWTH_ATTENTION_WEIGHT_WEAKNESS: float = 0.40
    GROWTH_ATTENTION_WEIGHT_DECLINE: float = 0.30
    GROWTH_ATTENTION_WEIGHT_MISTAKES: float = 0.30
    GROWTH_ATTENTION_WEIGHT_INACTIVITY: float = 0.00
    GROWTH_ALGORITHM_VERSION: str = "growth-1.0"

    # --- Recommendation policy (Phase 8) ---
    RECOMMENDATION_TOP_K: int = 5
    RECOMMENDATION_COOLDOWN_HOURS: int = 24
    RECOMMENDATION_WEIGHT_WEAKNESS: float = 0.30
    RECOMMENDATION_WEIGHT_DECLINE: float = 0.25
    RECOMMENDATION_WEIGHT_FAILURES: float = 0.20
    RECOMMENDATION_WEIGHT_LOW_CONF: float = 0.10
    RECOMMENDATION_WEIGHT_MATERIAL: float = 0.15
    RECOMMENDATION_PENALTY_RECENT_REC: float = 0.40
    RECOMMENDATION_ALGORITHM_VERSION: str = "rec-1.0"

    # --- Background work ---
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""
    WORKER_CONCURRENCY_DOCUMENTS: int = 2
    WORKER_CONCURRENCY_LEARNING: int = 4

    # --- Rate limits ---
    RATE_LIMIT_GLOBAL_PER_MINUTE: int = 300
    RATE_LIMIT_AI_PER_MINUTE: int = 30
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10

    # --- Observability (ADR-0020) ---
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    SENTRY_DSN: str | None = None
    TRACE_SAMPLE_RATE: float = 1.0

    @model_validator(mode="after")
    def _validate_environment_policy(self) -> Settings:
        """Fail safely: production demands real infrastructure config; dev/test may default."""
        # Route AI provider roles based on AI_PROVIDER
        if self.AI_PROVIDER == "gemini":
            if self.AI_GENERATION_PROVIDER == "stub":
                self.AI_GENERATION_PROVIDER = "gemini"
            if self.AI_STRUCTURED_PROVIDER == "stub":
                self.AI_STRUCTURED_PROVIDER = "gemini"
            if self.AI_PROVIDER_REGISTRY == "stub":
                self.AI_PROVIDER_REGISTRY = "gemini"
        if (
            self.AI_GENERATION_PROVIDER == "gemini"
            and self.AI_GENERATION_MODEL == "stub-generation"
        ):
            self.AI_GENERATION_MODEL = self.GEMINI_MODEL
        if (
            self.AI_STRUCTURED_PROVIDER == "gemini"
            and self.AI_STRUCTURED_MODEL == "stub-structured"
        ):
            self.AI_STRUCTURED_MODEL = self.GEMINI_MODEL

        if self.APP_ENV in ("staging", "production"):
            missing = [
                name
                for name in ("DATABASE_URL", "REDIS_URL", "CELERY_BROKER_URL", "JWT_PRIVATE_KEY")
                if not getattr(self, name)
            ]
            if missing:
                raise RuntimeError(
                    "Refusing to boot: required production configuration missing: "
                    + ", ".join(sorted(missing))
                )
            if self.REFRESH_COOKIE_SECURE is False:
                raise RuntimeError(
                    "Refusing to boot: REFRESH_COOKIE_SECURE must be true in "
                    "staging/production (refresh cookie is HttpOnly; Secure; SameSite=Strict)"
                )
            if self.AI_PROVIDER_REGISTRY == "stub":
                raise RuntimeError(
                    "Refusing to boot: AI_PROVIDER_REGISTRY=stub is not allowed outside dev/test"
                )
        return self

    # --- CORS helpers ---
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    def safe_summary(self) -> dict:
        """Redacted summary safe for logs and /readyz — never includes secrets (security-baseline §5)."""
        return {
            "app_env": self.APP_ENV,
            "app_version": self.APP_VERSION,
            "log_level": self.LOG_LEVEL,
            "database_configured": bool(self.DATABASE_URL),
            "runtime_database_configured": bool(self.DATABASE_RUNTIME_URL),
            "redis_configured": bool(self.REDIS_URL),
            "celery_broker_configured": bool(self.CELERY_BROKER_URL),
            "storage": {
                "provider": self.STORAGE_PROVIDER or "auto",
                "endpoint": (
                    self.STORAGE_ENDPOINT if self.STORAGE_PROVIDER != "supabase" else "supabase"
                ),
                "bucket": self.STORAGE_BUCKET,
                "access_key_id": _mask(self.STORAGE_ACCESS_KEY_ID),
                "supabase_configured": bool(self.SUPABASE_URL and self.SUPABASE_SECRET_KEY),
            },
            "ai": {
                "registry": self.AI_PROVIDER_REGISTRY,
                "provider": self.AI_PROVIDER,
                "model": self.GEMINI_MODEL if self.AI_PROVIDER == "gemini" else None,
                "roles": {
                    "generation": [self.AI_GENERATION_PROVIDER, self.AI_GENERATION_MODEL],
                    "structured": [self.AI_STRUCTURED_PROVIDER, self.AI_STRUCTURED_MODEL],
                    "embedding": [self.AI_EMBEDDING_PROVIDER, self.AI_EMBEDDING_MODEL],
                    "rerank": [self.AI_RERANKER_PROVIDER, self.AI_RERANKER_MODEL],
                    "evaluation": [self.AI_EVALUATION_PROVIDER, self.AI_EVALUATION_MODEL],
                    "vision": [self.AI_VISION_PROVIDER, self.AI_VISION_MODEL],
                },
            },
            "retrieval": {
                "top_k": self.RETRIEVAL_TOP_K,
                "rerank_to": self.RETRIEVAL_RERANK_TO,
                "sufficiency_tau": self.RETRIEVAL_SUFFICIENCY_TAU,
                "min_supporting_chunks": self.RETRIEVAL_MIN_SUPPORTING_CHUNKS,
            },
            "jwt_algorithm": self.JWT_ALGORITHM,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    """Test helper — drop the cached settings so env overrides take effect."""
    get_settings.cache_clear()
