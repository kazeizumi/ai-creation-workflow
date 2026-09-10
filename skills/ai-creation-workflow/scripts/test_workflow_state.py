#!/usr/bin/env python3
"""Behavior tests for stage transitions, targeted invalidation and delegation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("workflow_state.py")


def run(*args: str, expect: int = 0) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="workflow-state-") as raw:
        root = Path(raw)
        state_path = root / "state.json"
        state = {
            "schema_version": 2,
            "state_version": 1,
            "delegation_policy": {
                "status": "not_evaluated",
                "reason": None,
                "active_assignments": [],
            },
            "stages": [
                {
                    "id": "A",
                    "dependencies": [],
                    "input_fingerprints": {"brief": "v1"},
                    "status": "accepted",
                },
                {
                    "id": "B",
                    "dependencies": ["A"],
                    "input_fingerprints": {},
                    "status": "accepted",
                },
                {
                    "id": "C",
                    "dependencies": [],
                    "input_fingerprints": {},
                    "status": "accepted",
                },
            ],
            "external_jobs": [],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        assert "valid" in run("validate", str(state_path)).lower()
        run(
            "invalidate",
            str(state_path),
            "--stage",
            "A",
            "--input-key",
            "brief",
            "--new-fingerprint",
            "v2",
        )
        changed = json.loads(state_path.read_text(encoding="utf-8"))
        statuses = {stage["id"]: stage["status"] for stage in changed["stages"]}
        assert statuses == {"A": "stale", "B": "stale", "C": "accepted"}
        before = state_path.read_bytes()
        assert "No change" in run(
            "invalidate",
            str(state_path),
            "--stage",
            "A",
            "--input-key",
            "brief",
            "--new-fingerprint",
            "v2",
        )
        assert state_path.read_bytes() == before
        run("transition", str(state_path), "--stage", "A", "--to", "ready")
        assert "invalid transition" in run(
            "transition", str(state_path), "--stage", "A", "--to", "accepted", expect=2
        )
        run(
            "delegation",
            str(state_path),
            "--status",
            "declined",
            "--reason",
            "shared write target",
        )
        declined = json.loads(state_path.read_text(encoding="utf-8"))[
            "delegation_policy"
        ]
        assert declined["status"] == "declined" and declined["reason"]
        assignment = root / "assignment.json"
        assignment.write_text(
            json.dumps(
                {
                    "node_id": "C",
                    "input_packet": ["brief:v2"],
                    "write_scope": ["out/c.txt"],
                    "acceptance": ["artifact parses"],
                }
            ),
            encoding="utf-8",
        )
        run(
            "delegation",
            str(state_path),
            "--status",
            "delegated",
            "--reason",
            "independent output",
            "--assignment",
            str(assignment),
        )
        delegated = json.loads(state_path.read_text(encoding="utf-8"))[
            "delegation_policy"
        ]
        assert (
            delegated["status"] == "delegated"
            and len(delegated["active_assignments"]) == 1
        )
    print("workflow state tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
