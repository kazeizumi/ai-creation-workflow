#!/usr/bin/env python3
"""Install selected repository skills with backups and an explicit write flag."""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills"


def available() -> dict[str, Path]:
    return {path.name: path for path in SOURCE.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=str(Path.home() / ".agents" / "skills"))
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="perform the planned writes")
    args = parser.parse_args()
    catalog = available()
    selected = args.skill or sorted(catalog)
    unknown = sorted(set(selected) - set(catalog))
    if unknown:
        parser.error("unknown skills: " + ", ".join(unknown))
    target = Path(args.target).expanduser().resolve()
    if target == Path(target.anchor):
        parser.error("refusing filesystem root as target")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan = []
    for name in selected:
        destination = target / name
        backup = target / ".ai-creation-workflow-backups" / f"{name}-{stamp}" if destination.exists() else None
        plan.append((name, catalog[name], destination, backup))
        print(f"{name}: {destination}" + (f" (backup: {backup})" if backup else ""))
    if args.dry_run or not args.yes:
        print("Dry plan only. Repeat with --yes to install.")
        return 0
    target.mkdir(parents=True, exist_ok=True)
    for name, source, destination, backup in plan:
        if backup:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(destination, backup)
            shutil.rmtree(destination)
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"Installed {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
