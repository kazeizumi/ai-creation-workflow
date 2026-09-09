#!/usr/bin/env python3
"""Exercise recoverable retirement and restoration in a temporary directory."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("skill_transaction.py")


def run(*args: str) -> str:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def run_fail(*args: str) -> str:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
    if result.returncode == 0:
        raise AssertionError("command unexpectedly succeeded")
    return result.stdout + result.stderr


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="skill-lifecycle-") as raw:
        root = Path(raw)
        current = root / "skills" / "sample"
        current.mkdir(parents=True)
        (current / "SKILL.md").write_text("---\nname: sample\ndescription: test\n---\n", encoding="utf-8")
        archive = root / "archive"
        registry = root / "registry" / "skill-retirements.json"
        plan = root / "plans" / "sample-retire.json"
        rejected = run_fail(
            "prepare-retire", "--current", str(current), "--archive-root", str(current / "archive"),
            "--retirements", str(registry), "--plan", str(root / "plans" / "rejected.json"),
            "--skill-name", "../escape", "--evidence", "invalid fixture",
        )
        assert "outside the skill tree" in rejected or "invalid skill name" in rejected.lower()
        run("prepare-retire", "--current", str(current), "--archive-root", str(archive),
            "--retirements", str(registry), "--plan", str(plan), "--skill-name", "sample",
            "--replacement", "sample-next", "--evidence", "superseded in fixture")
        assert current.is_dir() and json.loads(plan.read_text(encoding="utf-8"))["status"] == "ready"
        run("retire", "--plan", str(plan), "--approved", "retire")
        assert not current.exists()
        record = json.loads(registry.read_text(encoding="utf-8"))["skills"]["sample"]
        assert Path(record["archive_path"]).is_dir() and record["status"] == "retired"
        duplicate = root / "duplicate" / "sample"
        duplicate.mkdir(parents=True)
        (duplicate / "SKILL.md").write_text("---\nname: sample\ndescription: duplicate\n---\n", encoding="utf-8")
        rejected = run_fail(
            "prepare-retire", "--current", str(duplicate), "--archive-root", str(archive),
            "--retirements", str(registry), "--plan", str(root / "plans" / "duplicate.json"),
            "--skill-name", "sample", "--evidence", "duplicate fixture",
        )
        assert "active retirement record" in rejected
        run("restore-retired", "--skill-name", "sample", "--retirements", str(registry), "--approved", "restore")
        assert (current / "SKILL.md").is_file()
        record = json.loads(registry.read_text(encoding="utf-8"))["skills"]["sample"]
        assert record["status"] == "active" and record["reactivated_at"]
    print("skill lifecycle tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
