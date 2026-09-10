#!/usr/bin/env python3
"""Validate and update resumable workflow state without broad invalidation."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

STAGE_STATUSES = {
    "pending",
    "ready",
    "running",
    "blocked",
    "review",
    "accepted",
    "failed",
    "stale",
}
TRANSITIONS = {
    "pending": {"ready", "blocked", "stale"},
    "ready": {"running", "blocked", "stale"},
    "running": {"review", "accepted", "failed", "blocked", "stale"},
    "blocked": {"ready", "failed", "stale"},
    "review": {"running", "accepted", "failed", "stale"},
    "accepted": {"stale"},
    "failed": {"ready", "stale"},
    "stale": {"ready", "blocked"},
}
DELEGATION_STATUSES = {"not_evaluated", "declined", "delegated"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: dict) -> None:
    path = path.resolve()
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def stage_map(state: dict) -> dict[str, dict]:
    stages = state.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("stages must be a non-empty list")
    result: dict[str, dict] = {}
    for stage in stages:
        stage_id = stage.get("id") if isinstance(stage, dict) else None
        if not isinstance(stage_id, str) or not stage_id:
            raise ValueError("every stage requires a non-empty id")
        if stage_id in result:
            raise ValueError(f"duplicate stage id: {stage_id}")
        result[stage_id] = stage
    return result


def validate_assignment(assignment: dict) -> list[str]:
    errors: list[str] = []
    for field in ("node_id", "input_packet", "write_scope", "acceptance"):
        value = assignment.get(field)
        if field == "node_id":
            if not isinstance(value, str) or not value:
                errors.append("delegation assignment requires node_id")
        elif not isinstance(value, list) or not value:
            errors.append(f"delegation assignment requires non-empty {field}")
    return errors


def validate_state(state: dict) -> list[str]:
    errors: list[str] = []
    try:
        stages = stage_map(state)
    except ValueError as error:
        return [str(error)]
    for stage_id, stage in stages.items():
        status = stage.get("status")
        if status not in STAGE_STATUSES:
            errors.append(f"{stage_id}: invalid status {status!r}")
        dependencies = stage.get("dependencies", [])
        if not isinstance(dependencies, list):
            errors.append(f"{stage_id}: dependencies must be a list")
            continue
        for dependency in dependencies:
            if dependency == stage_id:
                errors.append(f"{stage_id}: stage cannot depend on itself")
            elif dependency not in stages:
                errors.append(f"{stage_id}: unknown dependency {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visiting:
            errors.append(f"dependency cycle includes {stage_id}")
            return
        if stage_id in visited:
            return
        visiting.add(stage_id)
        for dependency in stages[stage_id].get("dependencies", []):
            if dependency in stages:
                visit(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)

    for stage_id in stages:
        visit(stage_id)

    policy = state.get("delegation_policy", {})
    status = policy.get("status", "not_evaluated")
    if status not in DELEGATION_STATUSES:
        errors.append(f"invalid delegation status: {status!r}")
    if status != "not_evaluated" and not str(policy.get("reason", "")).strip():
        errors.append("evaluated delegation requires a reason")
    assignments = policy.get("active_assignments", [])
    if not isinstance(assignments, list):
        errors.append("delegation active_assignments must be a list")
    else:
        for assignment in assignments:
            if not isinstance(assignment, dict):
                errors.append("delegation assignment must be an object")
            else:
                errors.extend(validate_assignment(assignment))
    if status == "delegated" and not assignments:
        errors.append("delegated status requires an active assignment")
    if status == "declined" and assignments:
        errors.append("declined delegation cannot keep active assignments")

    jobs = state.get("external_jobs", [])
    if isinstance(jobs, list):
        identities = [
            job.get("job_id") or job.get("prompt_id")
            for job in jobs
            if isinstance(job, dict)
        ]
        identities = [identity for identity in identities if identity]
        if len(identities) != len(set(identities)):
            errors.append("external job identities must be unique")
    return errors


def descendants(stages: dict[str, dict], start: str) -> set[str]:
    affected = {start}
    changed = True
    while changed:
        changed = False
        for stage_id, stage in stages.items():
            if stage_id not in affected and affected.intersection(
                stage.get("dependencies", [])
            ):
                affected.add(stage_id)
                changed = True
    return affected


def command_validate(args: argparse.Namespace) -> int:
    errors = validate_state(read_state(Path(args.state)))
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print("Workflow state valid")
    return 0


def command_transition(args: argparse.Namespace) -> int:
    path = Path(args.state)
    state = read_state(path)
    errors = validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    stages = stage_map(state)
    if args.stage not in stages:
        raise ValueError(f"unknown stage: {args.stage}")
    stage = stages[args.stage]
    current = stage["status"]
    if args.to == current:
        print(f"No change: {args.stage} already {current}")
        return 0
    if args.to not in TRANSITIONS[current]:
        raise ValueError(f"invalid transition: {current} -> {args.to}")
    stage["status"] = args.to
    if args.evidence:
        stage.setdefault("completion_evidence", []).append(args.evidence)
    state["updated_at"] = now_iso()
    state["state_version"] = int(state.get("state_version", 0)) + 1
    if not args.dry_run:
        write_state(path, state)
    print(
        f"Transition: {args.stage} {current} -> {args.to}"
        + (" (dry run)" if args.dry_run else "")
    )
    return 0


def command_invalidate(args: argparse.Namespace) -> int:
    path = Path(args.state)
    state = read_state(path)
    errors = validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    stages = stage_map(state)
    if args.stage not in stages:
        raise ValueError(f"unknown stage: {args.stage}")
    target = stages[args.stage]
    fingerprints = target.setdefault("input_fingerprints", {})
    previous = fingerprints.get(args.input_key)
    if previous == args.new_fingerprint:
        print("No change: input fingerprint is unchanged")
        return 0
    fingerprints[args.input_key] = args.new_fingerprint
    affected = descendants(stages, args.stage)
    changed: list[str] = []
    for stage_id in sorted(affected):
        stage = stages[stage_id]
        if stage.get("status") != "pending" and stage.get("status") != "stale":
            stage["status"] = "stale"
            changed.append(stage_id)
    state["updated_at"] = now_iso()
    state["state_version"] = int(state.get("state_version", 0)) + 1
    if not args.dry_run:
        write_state(path, state)
    print(
        f"Invalidated: {','.join(changed) if changed else 'none'}"
        + (" (dry run)" if args.dry_run else "")
    )
    return 0


def command_delegation(args: argparse.Namespace) -> int:
    path = Path(args.state)
    state = read_state(path)
    policy = state.setdefault("delegation_policy", {})
    assignments: list[dict] = []
    if args.status == "delegated":
        if not args.assignment:
            raise ValueError("delegated status requires --assignment")
        payload = json.loads(Path(args.assignment).read_text(encoding="utf-8"))
        assignments = [payload]
        errors = validate_assignment(payload)
        if errors:
            raise ValueError("; ".join(errors))
    policy.update(
        {
            "status": args.status,
            "reason": args.reason,
            "active_assignments": assignments,
        }
    )
    errors = validate_state(state)
    if errors:
        raise ValueError("; ".join(errors))
    state["updated_at"] = now_iso()
    state["state_version"] = int(state.get("state_version", 0)) + 1
    if not args.dry_run:
        write_state(path, state)
    print(
        f"Delegation decision: {args.status}" + (" (dry run)" if args.dry_run else "")
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("state")
    validate.set_defaults(func=command_validate)
    transition = commands.add_parser("transition")
    transition.add_argument("state")
    transition.add_argument("--stage", required=True)
    transition.add_argument("--to", required=True, choices=sorted(STAGE_STATUSES))
    transition.add_argument("--evidence")
    transition.add_argument("--dry-run", action="store_true")
    transition.set_defaults(func=command_transition)
    invalidate = commands.add_parser("invalidate")
    invalidate.add_argument("state")
    invalidate.add_argument("--stage", required=True)
    invalidate.add_argument("--input-key", required=True)
    invalidate.add_argument("--new-fingerprint", required=True)
    invalidate.add_argument("--dry-run", action="store_true")
    invalidate.set_defaults(func=command_invalidate)
    delegation = commands.add_parser("delegation")
    delegation.add_argument("state")
    delegation.add_argument(
        "--status", required=True, choices=["declined", "delegated"]
    )
    delegation.add_argument("--reason", required=True)
    delegation.add_argument("--assignment")
    delegation.add_argument("--dry-run", action="store_true")
    delegation.set_defaults(func=command_delegation)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
