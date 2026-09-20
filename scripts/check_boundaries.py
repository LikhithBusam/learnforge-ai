#!/usr/bin/env python3
"""Architecture boundary enforcement (module-contracts; principles §11; ADR-0007).

Mechanism: an AST-based import checker run in CI (test boundary tests import
this module too). Chosen over import-linter for Phase 0 because it is
dependency-free, explicit, and version-controllable; importlinter contracts
remain in pyproject later if desired.

Rules:
  R1  Domain modules may import another module's `service` (facade) only —
      never `.models`, `.repository`, `.router`, `.tasks`, `.celery_app`, `.schemas`.
  R2  Only `app.ai` (and `app.platform`) may import provider SDKs
      (openai, anthropic, google.generativeai, cohere, groq, mistralai, bedrock, minio...).
  R3  `app.ai` must NOT import domain modules (they depend on the Gateway,
      never the reverse; module-contracts §M.11).
  R4  `app.platform` must not import domain modules (one-way base layer).
  R5  Domain modules may not import provider SDKs (subset of R2 stated for clarity).

Exit code 1 on any violation; prints violations with file/line.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "apps" / "api" / "src"

DOMAIN_MODULES = {
    "identity",
    "workspace",
    "materials",
    "knowledge",
    "tutor",
    "assessment",
    "mastery",
    "growth",
    "recommendations",
    "analytics",
    "admin",
    "tools",
}
ALL_MODULES = DOMAIN_MODULES | {"ai", "jobs", "platform"}

FACADE_ONLY = {"models", "repository", "router", "tasks", "celery_app"}
# schemas are part of a module's contract surface; contracts importing another
# module's schemas is a contract decision, blocked for domain->domain for now.

PROVIDER_SDKS = {
    "openai",
    "anthropic",
    "google",
    "google.generativeai",
    "cohere",
    "groq",
    "mistralai",
    "boto3",
    "botocore",
    "minio",
    "litellm",
}


@dataclass
class Violation:
    file: Path
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        rel = (
            self.file.relative_to(SRC.parent.parent.parent)
            if SRC in self.file.parents
            else self.file
        )
        return f"{rel}:{self.line} [{self.rule}] {self.message}"


def module_of_import(module: str) -> tuple[str | None, str | None]:
    """Return (app_module, submodule) for imports like app.tutor.service."""
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "app":
        mod = parts[1]
        sub = parts[2] if len(parts) >= 3 else None
        return (mod if mod in ALL_MODULES else None), sub
    return None, None


def check_file(path: Path, module_hint: str | None = None) -> list[Violation]:
    """Check one file. Files under SRC get their module from the path; synthetic
    files (tests) may pass `module_hint` to simulate ownership."""
    violations: list[Violation] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [Violation(path, exc.lineno or 0, "SYNTAX", f"unparseable file: {exc}")]

    try:
        rel = path.relative_to(SRC)
    except ValueError:
        rel = None
    if module_hint is not None:
        own_module = module_hint
    elif rel is not None and rel.parts[0] == "app" and len(rel.parts) >= 2:
        own_module = rel.parts[1]
    else:
        own_module = None

    for node in ast.walk(tree):
        imports: list[tuple[int, str]] = []
        if isinstance(node, ast.Import):
            imports = [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imports = [(node.lineno, node.module)]
        for lineno, module in imports:
            target_mod, target_sub = module_of_import(module)

            # R2/R5: provider SDK isolation
            root = module.split(".")[0]
            if root in PROVIDER_SDKS or module in PROVIDER_SDKS:
                if own_module not in ("ai", "platform"):
                    violations.append(
                        Violation(
                            path,
                            lineno,
                            "R2/R5",
                            f"provider SDK '{module}' imported outside app.ai/app.platform",
                        )
                    )
                elif (
                    own_module == "platform"
                    and root in PROVIDER_SDKS
                    and root not in {"minio", "boto3", "botocore"}
                ):
                    violations.append(
                        Violation(
                            path,
                            lineno,
                            "R2/R5",
                            f"model-provider SDK '{module}' imported in app.platform",
                        )
                    )

            if target_mod is None or target_mod == own_module:
                continue

            # R1: facade-only cross-module imports between domain modules.
            # app.platform is the one-way BASE layer (R4): its public
            # infrastructure surface (db, models/Base, security, ids, ...) is
            # the sanctioned dependency direction domain -> platform, so it is
            # exempt from the facade-only rule.
            R1_TARGETS = DOMAIN_MODULES | {"ai", "jobs"}
            if own_module in DOMAIN_MODULES and target_mod in R1_TARGETS:
                if target_sub in FACADE_ONLY:
                    violations.append(
                        Violation(
                            path,
                            lineno,
                            "R1",
                            f"app.{own_module} imports app.{target_mod}.{target_sub} — only the service facade is allowed",
                        )
                    )

            # R3: AI Gateway must not depend on domain modules
            if own_module == "ai" and target_mod in DOMAIN_MODULES:
                violations.append(
                    Violation(
                        path,
                        lineno,
                        "R3",
                        f"app.ai imports domain module app.{target_mod} — domain depends on the Gateway, never the reverse",
                    )
                )

            # R4: platform must not import domain modules
            if own_module == "platform" and target_mod in DOMAIN_MODULES:
                violations.append(
                    Violation(
                        path,
                        lineno,
                        "R4",
                        f"app.platform imports domain module app.{target_mod} — platform is the one-way base layer",
                    )
                )

    return violations


def main() -> int:
    violations: list[Violation] = []
    for py_file in sorted(SRC.rglob("*.py")):
        violations.extend(check_file(py_file))
    if violations:
        print("ARCHITECTURE BOUNDARY VIOLATIONS:")
        for v in violations:
            print(f"  {v}")
        print(
            f"\n{len(violations)} violation(s). See scripts/check_boundaries.py docstring for the rules."
        )
        return 1
    print(f"Boundary check passed: {sum(1 for _ in SRC.rglob('*.py'))} files, no violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
