"""Unit tests for Phase 3 materials validation and upload policies."""

import pytest
from app.materials import service
from app.platform.config import get_settings
from app.platform.errors import ValidationError
from app.platform.ids import uuid7
from app.platform.storage import reset_storage


@pytest.fixture(autouse=True)
def _storage():
    reset_storage()
    yield
    reset_storage()


@pytest.mark.asyncio
async def test_upload_intent_rejects_non_pdf():
    user_id = uuid7()
    project_id = uuid7()

    # Non-pdf content type
    with pytest.raises(ValidationError, match="only PDF is permitted"):
        await service.create_upload_intent(
            owner_id=user_id,
            project_id=project_id,
            title="Notes",
            filename="notes.docx",
            content_type="application/msword",
            size_bytes=1000,
        )

    # Non-.pdf filename
    with pytest.raises(ValidationError, match="Filename must end with .pdf"):
        await service.create_upload_intent(
            owner_id=user_id,
            project_id=project_id,
            title="Notes",
            filename="notes.exe",
            content_type="application/pdf",
            size_bytes=1000,
        )

    # Zero or negative size
    with pytest.raises(ValidationError, match="greater than zero"):
        await service.create_upload_intent(
            owner_id=user_id,
            project_id=project_id,
            title="Notes",
            filename="notes.pdf",
            content_type="application/pdf",
            size_bytes=0,
        )

    # Oversized size
    settings = get_settings()
    with pytest.raises(ValidationError, match="exceeds maximum permitted limit"):
        await service.create_upload_intent(
            owner_id=user_id,
            project_id=project_id,
            title="Notes",
            filename="notes.pdf",
            content_type="application/pdf",
            size_bytes=settings.MAX_UPLOAD_BYTES + 1,
        )
