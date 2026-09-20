"""Architecture boundary tests — wrapper around scripts/check_boundaries.py.

These run in the unit stage so a boundary violation fails before integration
costs are paid. The script is the mechanism; this file makes it a test.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_boundaries as cb  # noqa: E402


def test_no_boundary_violations():
    violations: list[cb.Violation] = []
    for py_file in sorted(cb.SRC.rglob("*.py")):
        violations.extend(cb.check_file(py_file))
    assert not violations, "Architecture boundary violations:\n" + "\n".join(
        str(v) for v in violations
    )


def test_domain_module_facade_rule_blocks_repository_import(tmp_path):
    src = tmp_path / "offender.py"
    src.write_text("import app.knowledge.repository\n")
    violations = cb.check_file(src, module_hint="tutor")
    assert any(v.rule == "R1" for v in violations), violations


def test_facade_import_is_allowed(tmp_path):
    src = tmp_path / "ok.py"
    src.write_text("import app.knowledge.service\n")
    violations = cb.check_file(src, module_hint="tutor")
    assert not any(v.rule == "R1" for v in violations), violations


def test_provider_sdk_blocked_outside_ai(tmp_path):
    src = tmp_path / "offender2.py"
    src.write_text("import openai\n")
    violations = cb.check_file(src, module_hint="tutor")
    assert any("provider SDK" in v.message for v in violations), violations


def test_provider_sdk_allowed_in_ai(tmp_path):
    src = tmp_path / "ok2.py"
    src.write_text("import openai\n")
    violations = cb.check_file(src, module_hint="ai")
    assert not violations, violations


def test_ai_module_may_not_import_domain(tmp_path):
    src = tmp_path / "offender3.py"
    src.write_text("from app.tutor import service\n")
    violations = cb.check_file(src, module_hint="ai")
    assert any(v.rule == "R3" for v in violations), violations


def test_platform_may_not_import_domain(tmp_path):
    src = tmp_path / "offender4.py"
    src.write_text("import app.workspace.service\n")
    violations = cb.check_file(src, module_hint="platform")
    assert any(v.rule == "R4" for v in violations), violations
