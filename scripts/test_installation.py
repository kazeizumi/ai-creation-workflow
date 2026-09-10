#!/usr/bin/env python3
"""Verify that core skills remain usable when installed without repository siblings."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"
TEMPLATE_NAMES = (
    "00-project-control.md",
    "workflow-state.json",
    "h3-generation-contract.md",
)


def main() -> int:
    embedded = ROOT / "skills" / "ai-creation-workflow" / "assets" / "templates"
    public = ROOT / "templates"
    for name in TEMPLATE_NAMES:
        assert (embedded / name).is_file(), f"missing embedded template: {name}"
        assert (public / name).read_bytes() == (embedded / name).read_bytes(), (
            f"template drift: {name}"
        )
    with tempfile.TemporaryDirectory(prefix="skill-install-") as raw:
        target = Path(raw) / "skills"
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(INSTALLER),
                "--target",
                str(target),
                "--skill",
                "ai-creation-workflow",
                "--skill",
                "skill-governor",
                "--yes",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        workflow = target / "ai-creation-workflow"
        governor = target / "skill-governor"
        for name in TEMPLATE_NAMES:
            assert (workflow / "assets" / "templates" / name).is_file()
        assert (workflow / "scripts" / "workflow_state.py").is_file()
        assert (governor / "scripts" / "capability_gap.py").is_file()
        assert (
            governor / "assets" / "templates" / "retirement-evidence.json"
        ).is_file()
        assert not (target / "templates").exists(), (
            "installer must not depend on repository-level templates"
        )
    print("standalone installation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
