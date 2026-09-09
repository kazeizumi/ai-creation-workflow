#!/usr/bin/env python3
"""Run offline release checks for structure, secrets, links, JSON and Python."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", "__pycache__", ".pytest_cache", "work", "results", "backups"}
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b")
PRIVATE_PATH = re.compile(
    r"(?i)(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s]+[\\/]|/(?:home|Users)/[^/\s]+/)"
)
LOCAL_LINK = re.compile(r"\]\((?!https?://|#)([^)]+)\)")


def files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not any(part in IGNORED for part in path.relative_to(ROOT).parts)
    ]


def validate_skill(path: Path) -> list[str]:
    errors: list[str] = []
    skill = path / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return [f"{skill.relative_to(ROOT)}: invalid frontmatter"]
    front = match.group(1)
    name = re.search(r"(?m)^name:\s*([^\n]+)$", front)
    description = re.search(r"(?m)^description:\s*([^\n]+)$", front)
    if not name or not re.fullmatch(r"[a-z0-9-]{1,64}", name.group(1).strip()):
        errors.append(f"{skill.relative_to(ROOT)}: invalid name")
    if not description or "TODO" in description.group(1):
        errors.append(f"{skill.relative_to(ROOT)}: missing description")
    return errors


def main() -> int:
    errors: list[str] = []
    checked = files()
    for path in checked:
        relative = path.relative_to(ROOT)
        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
            except (SyntaxError, UnicodeDecodeError) as error:
                errors.append(f"{relative}: Python syntax: {error}")
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                errors.append(f"{relative}: JSON: {error}")
        if path.suffix.lower() in {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".ps1"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if JWT.search(text):
                errors.append(f"{relative}: possible JWT")
            if path.resolve() != Path(__file__).resolve() and PRIVATE_PATH.search(text):
                errors.append(f"{relative}: private absolute path")
            for link in LOCAL_LINK.findall(text) if path.suffix.lower() == ".md" else []:
                clean = urllib_unquote(link.split("#", 1)[0].strip().strip("<>"))
                if clean and not clean.startswith(("mailto:", "data:", "/")):
                    target = (path.parent / clean).resolve()
                    if not target.exists():
                        errors.append(f"{relative}: broken link {clean}")
    for skill in sorted((ROOT / "skills").iterdir()):
        if skill.is_dir():
            if not (skill / "SKILL.md").is_file():
                errors.append(f"skills/{skill.name}: missing SKILL.md")
            else:
                errors.extend(validate_skill(skill))
    forbidden: list[Path] = []
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
        ).stdout.decode("utf-8", errors="replace").split("\0")
        forbidden = [
            Path(item)
            for item in tracked
            if item and any(part in {"__pycache__", ".pytest_cache"} for part in Path(item).parts)
        ]
    except (OSError, subprocess.CalledProcessError):
        forbidden = [path.relative_to(ROOT) for path in ROOT.rglob("*") if path.name in {"__pycache__", ".pytest_cache"}]
    errors.extend(f"forbidden generated directory: {path}" for path in forbidden)
    if errors:
        print(f"Release verification failed: {len(errors)} issue(s)")
        for error in errors:
            print("ERROR", error)
        return 1
    print(f"Release verification passed: files={len(checked)} skills={len(list((ROOT / 'skills').iterdir()))}")
    return 0


def urllib_unquote(value: str) -> str:
    from urllib.parse import unquote

    return unquote(value)


if __name__ == "__main__":
    raise SystemExit(main())
