"""Application Capability Layer — tool executor skeleton (module-contracts §M.12; ai-tool-contracts).

Phase 0: registry + enforcement ORDER only. The tool catalogue
(search/evidence/learner-state/write tools) arrives with the tutor phase.
The enforcement sequence below is the security contract; each stage raises
NotImplementedError until its phase, never silently skipping.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    write: bool = False


@dataclass
class ToolInvocation:
    name: str
    arguments: dict
    justification: str | None = None
    feature: str = ""
    ai_request_id: str | None = None


@dataclass
class ToolResult:
    status: str  # success | validation_error | denied | execution_error
    data: dict | None = None
    error: dict | None = None
    invocation_id: str | None = None
    audit: dict = field(default_factory=dict)


class ToolRegistry:
    """Allow-list catalogue. Prohibited capabilities are structurally unregistrable
    (ai-tool-contracts §5) — enforced here at registration time."""

    PROHIBITED = {
        "execute_sql",
        "database_query",
        "arbitrary_http_request",
        "filesystem_access",
        "shell_execution",
    }

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, descriptor: ToolDescriptor) -> None:
        if descriptor.name in self.PROHIBITED or descriptor.name.startswith("generic_"):
            raise ValueError(f"Tool '{descriptor.name}' is prohibited by the capability boundary")
        self._tools[descriptor.name] = descriptor

    def get(self, name: str) -> ToolDescriptor | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDescriptor]:
        return list(self._tools.values())


registry = ToolRegistry()


class ToolExecutor:
    """Enforcement order (ai-tool-contracts §4) — Phase 0 skeleton with stages marked."""

    def invoke(self, scope, invocation: ToolInvocation) -> ToolResult:
        # 1. Feature allow-list check          -> phase: tutor/tools implementation
        # 2. Scope-injection check             -> phase: identity/authz phase
        # 3. JSON-Schema validation            -> phase: tutor/tools implementation
        # 4. Tool-specific semantic validation -> phase: tutor/tools implementation
        # 5. Authorization (read/write policy) -> phase: identity/authz phase
        # 6. Idempotency / dedup resolution    -> phase: with persistence
        # 7. Execution via owning module facade-> phase: module implementations
        # 8. Result shaping (size caps/redact) -> phase: tutor/tools implementation
        # 9. Audit record (always)             -> phase: persistence phase
        raise NotImplementedError(
            "Tool execution arrives with the capability-layer implementation phase"
        )
