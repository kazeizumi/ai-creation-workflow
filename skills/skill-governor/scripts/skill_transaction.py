#!/usr/bin/env python3
"""Prepare, activate, verify, and roll back auditable skill updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


def ensure_outside_tree(root: Path, targets: list[Path]) -> None:
    for target in targets:
        try:
            target.relative_to(root)
        except ValueError:
            continue
        raise ValueError(f"Control or archive path must stay outside the skill tree: {target}")


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


def protected_skill_path(path: Path) -> bool:
    folded = [part.casefold() for part in path.parts]
    return ".system" in folded or ("plugins" in folded and "cache" in folded)


def declared_skill_name(current: Path) -> str:
    text = (current / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^name:\s*([a-z0-9-]{1,64})\s*$", text)
    return match.group(1) if match else ""


def ensure_retirement_identity(current: Path, skill_name: str, retirements: Path) -> None:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", skill_name):
        raise ValueError("Skill name must use lowercase letters, digits, and hyphens.")
    if current.name != skill_name or declared_skill_name(current) != skill_name:
        raise ValueError("Skill name must match both the directory and SKILL.md frontmatter.")
    if retirements.exists():
        record = read_json(retirements).get("skills", {}).get(skill_name)
        if record and record.get("status") == "retired" and not record.get("reactivated_at"):
            raise ValueError(f"Skill already has an active retirement record: {skill_name}")


def command_prepare_retire(args: argparse.Namespace) -> int:
    current = safe_path(args.current, must_exist=True)
    archive_root = safe_path(args.archive_root)
    plan_path = safe_path(args.plan)
    retirements = safe_path(args.retirements)
    ensure_distinct([current, archive_root, plan_path, retirements])
    ensure_outside_tree(current, [archive_root, plan_path, retirements])
    if protected_skill_path(current):
        raise ValueError("System and plugin-cache skills cannot be retired by this command.")
    if not (current / "SKILL.md").is_file():
        raise ValueError("Current path is not a skill directory.")
    ensure_retirement_identity(current, args.skill_name, retirements)
    if plan_path.exists():
        raise FileExistsError(plan_path)
    payload = {
        "schema_version": 1,
        "status": "ready",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "skill_name": args.skill_name,
        "current": str(current),
        "current_tree_hash": tree_hash(current),
        "archive_root": str(archive_root),
        "retirements": str(retirements),
        "replacement": args.replacement or None,
        "evidence": args.evidence,
    }
    write_json(plan_path, payload)
    print(f"Retirement prepared: skill={args.skill_name}; plan={plan_path}; no files moved")
    return 0


def command_retire(args: argparse.Namespace) -> int:
    if args.approved != "retire":
        raise ValueError("Retirement requires --approved retire after reviewing the plan.")
    plan_path = safe_path(args.plan, must_exist=True)
    plan = read_json(plan_path)
    if plan.get("status") != "ready":
        raise RuntimeError("Retirement plan is not ready.")
    current = safe_path(plan["current"], must_exist=True)
    archive_root = safe_path(plan["archive_root"])
    retirements = safe_path(plan["retirements"])
    ensure_distinct([current, archive_root, plan_path, retirements])
    ensure_outside_tree(current, [archive_root, plan_path, retirements])
    if protected_skill_path(current):
        raise ValueError("System and plugin-cache skills cannot be retired by this command.")
    ensure_retirement_identity(current, str(plan.get("skill_name", "")), retirements)
    expected = plan.get("current_tree_hash")
    if tree_hash(current) != expected:
        raise RuntimeError("Skill changed after retirement preparation; prepare again.")
    archive_root.mkdir(parents=True, exist_ok=True)
    destination = archive_root / f"{plan['skill_name']}-{now_stamp()}"
    if destination.exists():
        raise FileExistsError(destination)
    previous_registry = retirements.read_bytes() if retirements.exists() else None
    original_plan = json.loads(json.dumps(plan))
    shutil.move(str(current), str(destination))
    try:
        if tree_hash(destination) != expected:
            raise RuntimeError("Archived skill failed hash verification.")
        data = read_json(retirements) if retirements.exists() else {"schema_version": 1, "skills": {}}
        data.setdefault("schema_version", 1)
        data.setdefault("skills", {})[plan["skill_name"]] = {
            "status": "retired",
            "replacement": plan.get("replacement"),
            "evidence": plan.get("evidence"),
            "original_path": str(current),
            "archive_path": str(destination),
            "tree_hash": expected,
            "retired_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "plan_path": str(plan_path),
            "reactivated_at": None,
        }
        write_json(retirements, data)
        plan["status"] = "executed"
        plan["archive_path"] = str(destination)
        write_json(plan_path, plan)
    except Exception:
        if not current.exists() and destination.exists():
            shutil.move(str(destination), str(current))
        if previous_registry is None:
            if retirements.exists():
                retirements.unlink()
        else:
            temporary = retirements.with_name(f".{retirements.name}.{os.getpid()}.rollback")
            temporary.write_bytes(previous_registry)
            temporary.replace(retirements)
        write_json(plan_path, original_plan)
        raise
    print(f"Retired {plan['skill_name']}; archive={destination}")
    return 0


def command_restore_retired(args: argparse.Namespace) -> int:
    if args.approved != "restore":
        raise ValueError("Restore requires --approved restore.")
    retirements = safe_path(args.retirements, must_exist=True)
    data = read_json(retirements)
    record = data.get("skills", {}).get(args.skill_name)
    if not record or record.get("status") != "retired" or record.get("reactivated_at"):
        raise ValueError(f"No active retirement record for {args.skill_name}")
    archive = safe_path(record["archive_path"], must_exist=True)
    target = safe_path(args.target or record["original_path"])
    ensure_distinct([archive, target, retirements])
    if target.exists():
        raise FileExistsError(target)
    expected = record.get("tree_hash")
    if tree_hash(archive) != expected:
        raise RuntimeError("Retired archive failed hash verification.")
    shutil.move(str(archive), str(target))
    try:
        if tree_hash(target) != expected:
            raise RuntimeError("Restored skill failed hash verification.")
        record["status"] = "active"
        record["reactivated_at"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        record["restored_path"] = str(target)
        write_json(retirements, data)
    except Exception:
        if not archive.exists() and target.exists():
            shutil.move(str(target), str(archive))
        raise
    print(f"Restored {args.skill_name}; target={target}")
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

    prepare_retire = commands.add_parser("prepare-retire", help="write a retirement plan without moving the skill")
    prepare_retire.add_argument("--current", required=True)
    prepare_retire.add_argument("--archive-root", required=True)
    prepare_retire.add_argument("--retirements", required=True)
    prepare_retire.add_argument("--plan", required=True)
    prepare_retire.add_argument("--skill-name", required=True)
    prepare_retire.add_argument("--replacement", default="")
    prepare_retire.add_argument("--evidence", required=True)
    prepare_retire.set_defaults(func=command_prepare_retire)

    retire = commands.add_parser("retire", help="move a reviewed skill into a verified archive")
    retire.add_argument("--plan", required=True)
    retire.add_argument("--approved", required=True)
    retire.set_defaults(func=command_retire)

    restore = commands.add_parser("restore-retired", help="restore a verified retired skill archive")
    restore.add_argument("--skill-name", required=True)
    restore.add_argument("--retirements", required=True)
    restore.add_argument("--target")
    restore.add_argument("--approved", required=True)
    restore.set_defaults(func=command_restore_retired)
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
