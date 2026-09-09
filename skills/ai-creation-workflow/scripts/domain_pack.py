#!/usr/bin/env python3
"""List and validate declarative domain packs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = SKILL_ROOT / "domain-packs"
REQUIRED = {
    "schema_version", "pack_id", "name", "description", "triggers", "guide",
    "stage_templates", "artifact_contracts", "specialist_lanes", "required_gates",
    "runtime_adapters", "failure_policy",
}


def load_pack(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def pack_paths(root: Path, selected: str = "") -> list[Path]:
    if selected:
        path = root / selected / "pack.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        return [path]
    return sorted(root.glob("*/pack.json"))


def validate_pack(path: Path, skill_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        pack = load_pack(path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [str(error)]
    missing = sorted(REQUIRED - set(pack))
    if missing:
        errors.append(f"{path}: missing {','.join(missing)}")
        return errors
    if pack["schema_version"] != 1:
        errors.append(f"{path}: schema_version must be 1")
    if pack["pack_id"] != path.parent.name:
        errors.append(f"{path}: pack_id must match directory name")
    for field in ("pack_id", "name", "description", "guide", "failure_policy"):
        if not isinstance(pack[field], str) or not pack[field].strip():
            errors.append(f"{path}: {field} must be a non-empty string")
    for field in ("triggers", "stage_templates", "specialist_lanes", "required_gates", "runtime_adapters"):
        if not isinstance(pack[field], list):
            errors.append(f"{path}: {field} must be an array")
    for field in ("triggers", "specialist_lanes", "runtime_adapters"):
        if isinstance(pack[field], list) and any(not isinstance(item, str) or not item.strip() for item in pack[field]):
            errors.append(f"{path}: {field} entries must be non-empty strings")
    guide = (skill_root / str(pack["guide"])).resolve()
    try:
        guide.relative_to(skill_root.resolve())
    except ValueError:
        errors.append(f"{path}: guide leaves skill root")
    else:
        if not guide.is_file():
            errors.append(f"{path}: guide not found: {pack['guide']}")
    stages = pack["stage_templates"] if isinstance(pack["stage_templates"], list) else []
    ids = [item.get("id") for item in stages if isinstance(item, dict)]
    if len(ids) != len(stages) or any(not item for item in ids) or len(set(ids)) != len(ids):
        errors.append(f"{path}: stage IDs must be present and unique")
        return errors
    for item in stages:
        if not isinstance(item.get("output"), str) or not item["output"].strip():
            errors.append(f"{path}: stage {item['id']} requires an output")
        if not isinstance(item.get("optional"), bool):
            errors.append(f"{path}: stage {item['id']} optional must be boolean")
    graph = {item["id"]: item.get("depends_on", []) for item in stages}
    optional = {item["id"]: bool(item.get("optional")) for item in stages}
    for stage_id, dependencies in graph.items():
        if not isinstance(dependencies, list) or any(dep not in graph for dep in dependencies):
            errors.append(f"{path}: invalid dependency in {stage_id}")
        elif not optional[stage_id] and any(optional.get(dep, False) for dep in dependencies):
            errors.append(f"{path}: required stage {stage_id} depends on optional stage")
    contracts = pack["artifact_contracts"]
    if not isinstance(contracts, dict) or set(contracts) != set(graph):
        errors.append(f"{path}: artifact_contracts must match stage IDs")
    else:
        for stage_id, contract in contracts.items():
            if not isinstance(contract, dict) or set(("inputs", "output", "acceptance")) - set(contract):
                errors.append(f"{path}: incomplete artifact contract for {stage_id}")
                continue
            if not isinstance(contract["inputs"], list) or not isinstance(contract["acceptance"], list):
                errors.append(f"{path}: artifact contract lists invalid for {stage_id}")
            elif any(not isinstance(value, str) or not value.strip() for value in contract["inputs"] + contract["acceptance"]):
                errors.append(f"{path}: artifact contract entries invalid for {stage_id}")
            if not isinstance(contract["output"], str) or not contract["output"].strip():
                errors.append(f"{path}: artifact contract output invalid for {stage_id}")
    gates = pack["required_gates"] if isinstance(pack["required_gates"], list) else []
    gate_ids: list[str] = []
    for gate in gates:
        if not isinstance(gate, dict) or not isinstance(gate.get("id"), str) or not isinstance(gate.get("when"), str):
            errors.append(f"{path}: gates require string id and when")
            continue
        gate_ids.append(gate["id"])
    if len(gate_ids) != len(set(gate_ids)):
        errors.append(f"{path}: gate IDs must be unique")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"{path}: dependency cycle at {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, []):
            if dependency in graph:
                visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for stage_id in graph:
        visit(stage_id)
    return errors


def validate_all(root: Path, selected: str = "") -> int:
    paths = pack_paths(root, selected)
    errors: list[str] = []
    if not paths:
        errors.append(f"no domain packs found under {root}")
    seen: set[str] = set()
    for path in paths:
        errors.extend(validate_pack(path, SKILL_ROOT))
        if path.parent.name in seen:
            errors.append(f"duplicate pack id: {path.parent.name}")
        seen.add(path.parent.name)
    print(f"Domain pack validation: packs={len(paths)} errors={len(errors)}")
    for error in errors:
        print(f"ERROR\t{error}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PACK_ROOT))
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--pack", default="")
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("--pack", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "validate":
            return validate_all(root, args.pack)
        if args.command == "list":
            for path in pack_paths(root):
                pack = load_pack(path)
                print(f"{pack['pack_id']}\t{pack['name']}\t{pack['description']}")
            return 0
        print(json.dumps(load_pack(pack_paths(root, args.pack)[0]), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
