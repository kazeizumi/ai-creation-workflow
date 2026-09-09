#!/usr/bin/env python3
"""Prepare, activate, verify, and roll back auditable skill updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def now_stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")


def safe_path(value: str, *, must_exist: bool = False) -> Path:
    path = Path(value).expanduser().resolve()
    if path == Path(path.anchor) or len(path.parts) < 3:
        raise ValueError(f"Refusing broad path: {path}")
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return path


def ensure_distinct(paths: list[Path]) -> None:
    normalized = [os.path.normcase(str(path)) for path in paths]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Baseline, current, upstream, staging, manifest, and backup targets must be distinct.")


def iter_files(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in IGNORED_SUFFIXES:
            continue
        result[relative.as_posix()] = path
    return result


def file_hash(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, path in sorted(iter_files(root).items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_hash(path) or ""))
        digest.update(b"\0")
    return digest.hexdigest()


def classify(base: str | None, current: str | None, upstream: str | None) -> tuple[str, str | None]:
    if current == upstream:
        return ("unchanged" if current is not None else "deleted"), "current" if current else None
    if current == base:
        return ("take-upstream" if upstream is not None else "upstream-delete"), "upstream" if upstream else None
    if upstream == base:
        return ("keep-local" if current is not None else "local-delete"), "current" if current else None
    if base is None:
        if current is None:
            return "upstream-add", "upstream"
        if upstream is None:
            return "local-add", "current"
        return "conflict-both-add", None
    if current is None and upstream is None:
        return "deleted", None
    if current is None:
        return "conflict-local-delete-upstream-edit", None
    if upstream is None:
        return "conflict-upstream-delete-local-edit", None
    return "conflict-both-edit", None


def copy_selected(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def command_prepare(args: argparse.Namespace) -> int:
    baseline = safe_path(args.baseline, must_exist=True)
    current = safe_path(args.current, must_exist=True)
    upstream = safe_path(args.upstream, must_exist=True)
    staging = safe_path(args.staging)
    manifest = safe_path(args.manifest)
    ensure_distinct([baseline, current, upstream, staging, manifest])
    if staging.exists():
        raise FileExistsError(f"Staging path already exists: {staging}")
    staging.mkdir(parents=True)

    trees = {"baseline": iter_files(baseline), "current": iter_files(current), "upstream": iter_files(upstream)}
    decisions: list[dict] = []
    conflicts = 0
    for relative in sorted(set().union(*(set(tree) for tree in trees.values()))):
        hashes = {name: file_hash(tree.get(relative)) for name, tree in trees.items()}
        action, source_name = classify(hashes["baseline"], hashes["current"], hashes["upstream"])
        if action.startswith("conflict"):
            conflicts += 1
        elif source_name:
            copy_selected(trees[source_name][relative], staging / Path(relative))
        decisions.append({"path": relative, **hashes, "action": action, "selected": source_name})

    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "status": "conflict" if conflicts else "ready",
        "baseline": str(baseline),
        "current": str(current),
        "upstream": str(upstream),
        "staging": str(staging),
        "current_tree_hash": tree_hash(current),
        "upstream_tree_hash": tree_hash(upstream),
        "staging_tree_hash": tree_hash(staging),
        "counts": dict(Counter(item["action"] for item in decisions)),
        "conflict_count": conflicts,
        "files": decisions,
    }
    write_json(manifest, payload)
    print(f"Prepared {len(decisions)} files; status={payload['status']}; conflicts={conflicts}; manifest={manifest}")
    return 2 if conflicts else 0


def make_backup(current: Path, backup_root: Path, skill_name: str) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    destination = backup_root / f"{skill_name}-{now_stamp()}"
    suffix = 1
    while destination.exists():
        destination = backup_root / f"{skill_name}-{now_stamp()}-{suffix}"
        suffix += 1
    content = destination / "content"
    shutil.copytree(current, content, symlinks=True)
    payload = {
        "schema_version": 1,
        "skill_name": skill_name,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "original_path": str(current),
        "content_path": str(content),
        "tree_hash": tree_hash(current),
        "file_count": len(iter_files(current)),
    }
    write_json(destination / "backup-manifest.json", payload)
    if tree_hash(content) != payload["tree_hash"]:
        raise RuntimeError("Backup verification failed")
    return destination


def command_backup(args: argparse.Namespace) -> int:
    current = safe_path(args.current, must_exist=True)
    backup_root = safe_path(args.backup_root)
    ensure_distinct([current, backup_root])
    destination = make_backup(current, backup_root, args.skill_name)
    print(f"Backup verified: {destination}")
    return 0


def command_verify_backup(args: argparse.Namespace) -> int:
    manifest = safe_path(args.backup_manifest, must_exist=True)
    payload = read_json(manifest)
    content = safe_path(payload["content_path"], must_exist=True)
    actual = tree_hash(content)
    expected = payload.get("tree_hash")
    if actual != expected:
        print(f"Backup mismatch: expected={expected} actual={actual}")
        return 2
    print(f"Backup valid: files={payload.get('file_count')} hash={actual}")
    return 0


def command_activate(args: argparse.Namespace) -> int:
    current = safe_path(args.current, must_exist=True)
    staging = safe_path(args.staging, must_exist=True)
    manifest = safe_path(args.manifest, must_exist=True)
    backup_root = safe_path(args.backup_root)
    ensure_distinct([current, staging, manifest, backup_root])
    if current.parent != staging.parent:
        raise ValueError("Staging must be a sibling of current for an atomic directory switch.")
    plan = read_json(manifest)
    if plan.get("status") != "ready" or plan.get("conflict_count"):
        raise RuntimeError("Update plan is not conflict-free.")
    if Path(plan.get("current", "")).resolve() != current or Path(plan.get("staging", "")).resolve() != staging:
        raise RuntimeError("Manifest paths do not match activation targets.")
    if tree_hash(current) != plan.get("current_tree_hash"):
        raise RuntimeError("Current skill changed after preparation; prepare again.")
    if tree_hash(staging) != plan.get("staging_tree_hash"):
        raise RuntimeError("Staging content changed after preparation.")

    backup = make_backup(current, backup_root, args.skill_name)
    displaced = current.with_name(f".{current.name}.replaced-{now_stamp()}")
    if displaced.exists():
        raise FileExistsError(displaced)
    current.rename(displaced)
    try:
        staging.rename(current)
        if tree_hash(current) != plan.get("staging_tree_hash"):
            raise RuntimeError("Activated tree hash does not match staging manifest.")
    except Exception:
        if current.exists():
            failed = current.with_name(f".{current.name}.failed-{now_stamp()}")
            current.rename(failed)
        displaced.rename(current)
        raise
    replaced = backup / "replaced-original"
    shutil.move(str(displaced), str(replaced))
    print(f"Activated {current}; backup={backup}; previous={replaced}")
    return 0


def command_rollback(args: argparse.Namespace) -> int:
    current = safe_path(args.current, must_exist=True)
    manifest = safe_path(args.backup_manifest, must_exist=True)
    payload = read_json(manifest)
    content = safe_path(payload["content_path"], must_exist=True)
    expected = payload.get("tree_hash")
    if tree_hash(content) != expected:
        raise RuntimeError("Backup content failed verification.")
    restore_stage = current.with_name(f".{current.name}.restore-{now_stamp()}")
    displaced = current.with_name(f".{current.name}.before-rollback-{now_stamp()}")
    if restore_stage.exists() or displaced.exists():
        raise FileExistsError("Rollback staging path already exists.")
    shutil.copytree(content, restore_stage, symlinks=True)
    if tree_hash(restore_stage) != expected:
        raise RuntimeError("Rollback staging verification failed.")
    current.rename(displaced)
    try:
        restore_stage.rename(current)
        if tree_hash(current) != expected:
            raise RuntimeError("Rollback verification failed after switch.")
    except Exception:
        if current.exists():
            failed = current.with_name(f".{current.name}.rollback-failed-{now_stamp()}")
            current.rename(failed)
        displaced.rename(current)
        raise
    recovery = manifest.parent / f"replaced-after-rollback-{now_stamp()}"
    shutil.move(str(displaced), str(recovery))
    print(f"Rollback complete: {current}; replaced version preserved at {recovery}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="three-way compare and build a conflict-free staging tree")
    for name in ("baseline", "current", "upstream", "staging", "manifest"):
        prepare.add_argument(f"--{name.replace('_', '-')}", required=True)
    prepare.set_defaults(func=command_prepare)

    backup = commands.add_parser("backup", help="create and verify a recoverable skill backup")
    backup.add_argument("--current", required=True)
    backup.add_argument("--backup-root", required=True)
    backup.add_argument("--skill-name", required=True)
    backup.set_defaults(func=command_backup)

    verify = commands.add_parser("verify-backup", help="verify a backup manifest and its content")
    verify.add_argument("--backup-manifest", required=True)
    verify.set_defaults(func=command_verify_backup)

    activate = commands.add_parser("activate", help="atomically switch a prepared sibling staging tree")
    activate.add_argument("--current", required=True)
    activate.add_argument("--staging", required=True)
    activate.add_argument("--manifest", required=True)
    activate.add_argument("--backup-root", required=True)
    activate.add_argument("--skill-name", required=True)
    activate.set_defaults(func=command_activate)

    rollback = commands.add_parser("rollback", help="restore a verified backup and preserve the replaced version")
    rollback.add_argument("--current", required=True)
    rollback.add_argument("--backup-manifest", required=True)
    rollback.set_defaults(func=command_rollback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
