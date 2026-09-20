"""Object storage abstraction (ADR-0016) — infrastructure only.

Conceptual operations supported: create upload URL, upload object, retrieve
metadata, create download URL, delete object. The materials *workflow* does
not exist yet (phase boundary); the Materials module will consume this
provider in a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.platform.config import Settings


@dataclass
class ObjectMeta:
    key: str
    size_bytes: int | None
    etag: str | None
    last_modified: str | None
    content_type: str | None


class StorageProvider:
    """Interface — infrastructure implementations register against this shape."""

    def healthcheck(self) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def create_upload_url(
        self, key: str, content_type: str = "application/pdf"
    ) -> str:  # pragma: no cover
        raise NotImplementedError

    def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    def head_object(self, key: str) -> ObjectMeta | None:  # pragma: no cover
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes | None:  # pragma: no cover
        raise NotImplementedError

    def create_download_url(
        self, key: str, ttl_seconds: int | None = None
    ) -> str:  # pragma: no cover
        raise NotImplementedError

    def delete_object(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError


class MinioStorage(StorageProvider):
    """Dev/prototype implementation against MinIO (S3-compatible)."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: object | None = None

    def _ensure_client(self):
        if self._client is None:
            from minio import Minio  # optional dependency group `storage`

            endpoint = self._settings.STORAGE_ENDPOINT
            # minio client expects host[:port]; infer secure flag from scheme
            secure = endpoint.startswith("https://")
            host = endpoint.split("://", 1)[-1]
            self._client = Minio(  # type: ignore[assignment] # concrete client held as object
                host,
                access_key=self._settings.STORAGE_ACCESS_KEY_ID,
                secret_key=self._settings.STORAGE_SECRET_ACCESS_KEY,
                secure=secure,
                region=self._settings.STORAGE_REGION,
            )
        return self._client

    def ensure_bucket(self) -> None:
        client = self._ensure_client()
        bucket = self._settings.STORAGE_BUCKET
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

    def healthcheck(self) -> dict:
        try:
            client = self._ensure_client()
            ok = client.bucket_exists(self._settings.STORAGE_BUCKET)
            return {"status": "ok" if ok else "degraded", "bucket": self._settings.STORAGE_BUCKET}
        except Exception as exc:  # noqa: BLE001 - probe must not raise
            return {"status": "error", "detail": type(exc).__name__}

    def create_upload_url(self, key: str, content_type: str = "application/pdf") -> str:

        client = self._ensure_client()
        return client.presigned_put_object(
            self._settings.STORAGE_BUCKET,
            key,
            expires=timedelta(seconds=self._settings.STORAGE_PRESIGN_TTL_SECONDS),
        ) + (f"?X-Amz-Content-Type={content_type}" if content_type else "")

    def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        import io

        client = self._ensure_client()
        client.put_object(
            self._settings.STORAGE_BUCKET,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def head_object(self, key: str) -> ObjectMeta | None:
        client = self._ensure_client()
        try:
            stat = client.stat_object(self._settings.STORAGE_BUCKET, key)
        except Exception:  # noqa: BLE001 - missing object is a normal outcome
            return None
        return ObjectMeta(
            key=key,
            size_bytes=stat.size,
            etag=stat.etag,
            last_modified=stat.last_modified.isoformat() if stat.last_modified else None,
            content_type=stat.content_type,
        )

    def get_bytes(self, key: str) -> bytes | None:
        client = self._ensure_client()
        try:
            response = client.get_object(self._settings.STORAGE_BUCKET, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception:  # noqa: BLE001
            return None

    def create_download_url(self, key: str, ttl_seconds: int | None = None) -> str:
        client = self._ensure_client()
        return client.presigned_get_object(
            self._settings.STORAGE_BUCKET,
            key,
            expires=timedelta(seconds=ttl_seconds or self._settings.STORAGE_PRESIGN_TTL_SECONDS),
        )

    def delete_object(self, key: str) -> None:
        client = self._ensure_client()
        client.remove_object(self._settings.STORAGE_BUCKET, key)


class SupabaseStorage(StorageProvider):
    """Cloud-first implementation against Supabase Storage (ADR-0022).

    Talks to the Supabase Storage REST API (``{SUPABASE_URL}/storage/v1``) with
    the server-side secret key (service_role) via httpx — no additional SDK.
    The key is sent ONLY to the configured Supabase URL, never logged, never
    embedded in returned URLs (signed URLs carry their own scoped token).
    The bucket is private; downloads go through short-TTL signed URLs.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._base = settings.SUPABASE_URL.rstrip("/") + "/storage/v1"
        self._client: object | None = None

    def _ensure_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                base_url=self._base,
                headers={
                    "Authorization": f"Bearer {self._settings.SUPABASE_SECRET_KEY}",
                    "apikey": self._settings.SUPABASE_SECRET_KEY,
                },
                timeout=15.0,
            )
        return self._client

    @staticmethod
    def _bucket_missing(response) -> bool:
        """Supabase returns HTTP 400 with a 404 body for missing buckets (not HTTP 404)."""
        if response.status_code == 404:
            return True
        if response.status_code == 400:
            try:
                return str(response.json().get("statusCode")) == "404"
            except Exception:  # noqa: BLE001
                return False
        return False

    def ensure_bucket(self) -> None:
        client = self._ensure_client()
        bucket = self._settings.STORAGE_BUCKET
        response = client.get(f"/bucket/{bucket}")
        if self._bucket_missing(response):
            created = client.post("/bucket", json={"name": bucket, "public": False})
            created.raise_for_status()
        elif response.status_code != 200:
            raise RuntimeError(f"Supabase bucket check failed: HTTP {response.status_code}")

    def healthcheck(self) -> dict:
        try:
            client = self._ensure_client()
            response = client.get(f"/bucket/{self._settings.STORAGE_BUCKET}")
            if response.status_code == 200:
                body = response.json()
                return {
                    "status": "ok",
                    "bucket": self._settings.STORAGE_BUCKET,
                    "public": bool(body.get("public", True)),
                }
            if self._bucket_missing(response):
                return {"status": "degraded", "detail": "bucket missing"}
            return {"status": "error", "detail": f"HTTP {response.status_code}"}
        except Exception as exc:  # noqa: BLE001 - probe must not raise
            return {"status": "error", "detail": type(exc).__name__}

    def create_upload_url(self, key: str, content_type: str = "application/pdf") -> str:
        import re

        client = self._ensure_client()
        safe_key = re.sub(r"[^A-Za-z0-9/_.\-]", "_", key)
        response = client.post(
            f"/object/upload/sign/{self._settings.STORAGE_BUCKET}/{safe_key}",
            json={"expiresIn": self._settings.STORAGE_PRESIGN_TTL_SECONDS},
        )
        response.raise_for_status()
        signed = response.json().get("url", "")
        return f"{self._settings.SUPABASE_URL.rstrip('/')}/storage/v1{signed}"

    def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        import re

        client = self._ensure_client()
        safe_key = re.sub(r"[^A-Za-z0-9/_.\-]", "_", key)
        response = client.post(
            f"/object/{self._settings.STORAGE_BUCKET}/{safe_key}",
            content=data,
            headers={"content-type": content_type, "x-upsert": "true"},
        )
        response.raise_for_status()

    def head_object(self, key: str) -> ObjectMeta | None:
        import re

        client = self._ensure_client()
        safe_key = re.sub(r"[^A-Za-z0-9/_.\-]", "_", key)
        response = client.head(f"/object/{self._settings.STORAGE_BUCKET}/{safe_key}")
        if response.status_code != 200:
            return None
        return ObjectMeta(
            key=key,
            size_bytes=(
                int(response.headers["content-length"])
                if "content-length" in response.headers
                else None
            ),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            content_type=response.headers.get("content-type"),
        )

    def get_bytes(self, key: str) -> bytes | None:
        import re

        client = self._ensure_client()
        safe_key = re.sub(r"[^A-Za-z0-9/_.\-]", "_", key)
        response = client.get(f"/object/{self._settings.STORAGE_BUCKET}/{safe_key}")
        if response.status_code != 200:
            return None
        return response.content

    def create_download_url(self, key: str, ttl_seconds: int | None = None) -> str:
        import re

        client = self._ensure_client()
        safe_key = re.sub(r"[^A-Za-z0-9/_.\-]", "_", key)
        response = client.post(
            f"/object/sign/{self._settings.STORAGE_BUCKET}/{safe_key}",
            json={"expiresIn": ttl_seconds or self._settings.STORAGE_PRESIGN_TTL_SECONDS},
        )
        response.raise_for_status()
        signed = response.json().get("signedURL", "")
        return f"{self._settings.SUPABASE_URL.rstrip('/')}/storage/v1{signed}"

    def delete_object(self, key: str) -> None:
        import re

        client = self._ensure_client()
        safe_key = re.sub(r"[^A-Za-z0-9/_.\-]", "_", key)
        response = client.delete(f"/object/{self._settings.STORAGE_BUCKET}/{safe_key}")
        response.raise_for_status()


class InMemoryStorage(StorageProvider):
    """CI/test implementation — no network, no credentials."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def healthcheck(self) -> dict:
        return {"status": "ok", "implementation": "in-memory"}

    def create_upload_url(self, key: str, content_type: str = "application/pdf") -> str:
        return f"http://storage.local/upload/{key}"

    def upload_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        self._objects[key] = data

    def head_object(self, key: str) -> ObjectMeta | None:
        if key not in self._objects:
            return None
        return ObjectMeta(
            key=key,
            size_bytes=len(self._objects[key]),
            etag=None,
            last_modified=None,
            content_type=None,
        )

    def get_bytes(self, key: str) -> bytes | None:
        return self._objects.get(key)

    def create_download_url(self, key: str, ttl_seconds: int | None = None) -> str:
        return f"http://storage.local/download/{key}"

    def delete_object(self, key: str) -> None:
        self._objects.pop(key, None)


_provider: StorageProvider | None = None


def init_storage(settings: Settings) -> StorageProvider:
    global _provider
    if _provider is None:
        chosen = settings.STORAGE_PROVIDER.strip().lower()
        if chosen == "supabase":
            if not (settings.SUPABASE_URL and settings.SUPABASE_SECRET_KEY):
                raise RuntimeError(
                    "STORAGE_PROVIDER=supabase requires SUPABASE_URL and SUPABASE_SECRET_KEY"
                )
            _provider = SupabaseStorage(settings)
        elif chosen == "minio":
            _provider = MinioStorage(settings)
        elif settings.APP_ENV in ("development", "test") and not settings.STORAGE_ACCESS_KEY_ID:
            _provider = InMemoryStorage()
        else:
            _provider = MinioStorage(settings)
    return _provider


def get_storage() -> StorageProvider:
    if _provider is None:
        raise RuntimeError("Storage provider not initialized")
    return _provider


def reset_storage() -> None:
    global _provider
    _provider = None
