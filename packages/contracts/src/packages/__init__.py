"""Shared contracts package.

Technology-neutral DTOs shared between API, workers, and (later) the generated
frontend client. Phase 0: the AI schemas live in the backend (app.ai.schemas)
and are exported here as re-exports to avoid duplication; the OpenAPI
generated-client flow (ADR-0011) begins with the first product endpoints.
"""

from __future__ import annotations
