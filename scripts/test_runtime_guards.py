#!/usr/bin/env python3
"""Regression tests for runner operations that must remain side-effect free."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "minimax-h3-cloud" / "scripts" / "run_batch.py"
EXAMPLE = ROOT / "examples" / "minimal-project" / "cloud-h3-batch.json"
sys.path.insert(0, str(RUNNER.parent))
import run_batch  # noqa: E402


def dry_run(manifest: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER), str(manifest), "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)


def resume(manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), str(manifest), "--resume"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="runtime-guards-") as raw:
        folder = Path(raw)
        payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        existing = folder / "existing-state.json"
        existing.write_text('{"sentinel":"keep"}\n', encoding="utf-8")
        payload["state_file"] = str(existing)
        manifest = folder / "existing.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        dry_run(manifest)
        assert existing.read_text(encoding="utf-8") == '{"sentinel":"keep"}\n'

        absent = folder / "absent-state.json"
        payload["state_file"] = str(absent)
        manifest = folder / "absent.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        dry_run(manifest)
        assert not absent.exists()

        output = (folder / "work" / "cloud-results" / "G01.mp4").resolve()
        uncertain = {
            "instance_uuid": payload["instance_uuid"],
            "phase": "submitting",
            "panel_url": None,
            "jobs": [{
                "name": "G01",
                "workflow_id": payload["jobs"][0]["workflow_id"],
                "output": str(output),
                "status": "pending"
            }],
            "shutdown": "not_started"
        }
        absent.write_text(json.dumps(uncertain), encoding="utf-8")
        before = absent.read_bytes()
        result = resume(manifest)
        assert result.returncode != 0 and "no prompt_id was recorded" in (result.stdout + result.stderr)
        assert absent.read_bytes() == before

        recorded = json.loads(json.dumps(uncertain))
        recorded["jobs"][0]["prompt_id"] = "prompt-existing-123"
        tasks = run_batch.resumable_tasks(
            {"jobs": [{**payload["jobs"][0], "output": str(output)}]}, recorded
        )
        assert len(tasks) == 1 and tasks[0]["prompt_id"] == "prompt-existing-123"
    print("runtime guard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
