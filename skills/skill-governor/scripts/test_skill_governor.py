#!/usr/bin/env python3
"""Portable smoke test for discovery, mapping, reporting and validation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("skill_registry.py")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def run(*args: str) -> str:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
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
            "overlap_group": [],
        }
        write(roadmap, json.dumps({"schema_version": 2, "skills": {"alpha-skill": route("Creates alpha.", "primary"), "beta-skill": route("Validates beta.", "complementary")}}))
        source_row = lambda: {"kind": "local", "license": "MIT", "local_modifications": False}
        write(sources, json.dumps({"schema_version": 1, "skills": {"alpha-skill": source_row(), "beta-skill": source_row()}}))
        common = ["--registry", str(registry), "--roadmap", str(roadmap), "--sources", str(sources)]
        output = run(*common, "scan", "--shared-root", str(shared), "--system-root", str(system), "--no-plugins")
        assert "Scanned 2 skills" in output
        output = run(*common, "report", "--lane", "test")
        assert "alpha-skill" in output and "beta-skill" in output
        output = run(*common, "validate")
        assert "errors=0" in output
    print("skill-governor smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
