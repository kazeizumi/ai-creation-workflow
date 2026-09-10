#!/usr/bin/env python3
"""Portable smoke test for discovery, mapping, reporting and validation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("skill_registry.py")
AUDIT_SCRIPT = Path(__file__).with_name("skill_audit.py")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def run_audit(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(AUDIT_SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="skill-governor-test-") as raw:
        root = Path(raw)
        shared = root / "shared"
        system = root / "system"
        system.mkdir()
        write(shared / "alpha-skill" / "SKILL.md", "---\nname: alpha-skill\ndescription: Creates alpha artifacts.\n---\n\n# Alpha\n")
        write(shared / "beta-skill" / "SKILL.md", "---\nname: beta-skill\ndescription: Validates beta artifacts.\n---\n\n# Beta\n")
        registry = root / "registry" / "skill-registry.json"
        roadmap = root / "registry" / "skill-roadmap.json"
        sources = root / "registry" / "skill-sources.json"
        route = lambda brief, role: {
            "lane": "test",
            "stage": "smoke",
            "brief": brief,
            "use_when": "The smoke test runs.",
            "boundary": "Test fixture only.",
            "role": role,
            "review_level": "full-reviewed",
            "overlap_group": ["test-overlap"],
        }
        write(roadmap, json.dumps({"schema_version": 2, "skills": {"alpha-skill": route("Creates alpha.", "primary"), "beta-skill": route("Validates beta.", "alternate")}}))
        source_row = lambda: {"kind": "local", "license": "MIT", "local_modifications": False}
        write(sources, json.dumps({"schema_version": 1, "skills": {"alpha-skill": source_row(), "beta-skill": source_row()}}))
        common = ["--registry", str(registry), "--roadmap", str(roadmap), "--sources", str(sources)]
        output = run(*common, "scan", "--shared-root", str(shared), "--system-root", str(system), "--no-plugins")
        assert "Scanned 2 skills" in output
        output = run(*common, "report", "--lane", "test")
        assert "alpha-skill" in output and "beta-skill" in output
        output = run(*common, "duplicates")
        assert "alpha-skill" in output and "beta-skill" in output
        output = run(*common, "validate")
        assert "errors=0" in output
        output = run(*common, "package-check", "--package-root", str(shared))
        assert "errors=0" in output
        run(*common, "record-outcome", "--skill", "alpha-skill", "--task-id", "fixture-1",
            "--verdict", "pass", "--source", "test", "--fit", "5", "--output", "5",
            "--reliability", "4", "--efficiency", "4", "--maintainability", "4",
            "--uniqueness", "3", "--safety", "5", "--evidence", "temporary fixture passed")
        usage = root / "registry" / "skill-usage.json"
        retirements = root / "registry" / "skill-retirements.json"
        audit_json = root / "audit.json"
        audit_common = ["--registry", str(registry), "--roadmap", str(roadmap), "--sources", str(sources),
                        "--usage", str(usage), "--retirements", str(retirements)]
        run_audit(*audit_common, "record-use", "--skill", "alpha-skill", "--task-id", "fixture-1",
                  "--result", "completed", "--reason", "temporary fixture")
        run_audit(*audit_common, "audit", "--output-json", str(audit_json))
        audit = json.loads(audit_json.read_text(encoding="utf-8"))
        alpha = next(item for item in audit["skills"] if item["name"] == "alpha-skill")
        assert alpha["quality_tasks"] == 1 and alpha["usage"]["recent_events"] == 1
        assert alpha["action"] in {"trial-review", "compare", "keep-core-probation"}
    print("skill-governor smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
