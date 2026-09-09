#!/usr/bin/env python3
"""Functional skill routing registry with versioned quality evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE.parent / "registry" / "skill-registry.json"
DEFAULT_ROADMAP = HERE.parent / "registry" / "skill-roadmap.json"
DEFAULT_SOURCES = HERE.parent / "registry" / "skill-sources.json"
DEFAULT_SHARED_ROOT = Path.home() / ".agents" / "skills"
DEFAULT_SYSTEM_ROOT = Path.home() / ".codex" / "skills" / ".system"
DEFAULT_PLUGIN_CACHE = Path.home() / ".codex" / "plugins" / "cache"
DEFAULT_CODEX_CONFIG = Path.home() / ".codex" / "config.toml"

ROUTE_REQUIRED = ("lane", "stage", "brief", "use_when", "boundary")
REVIEW_LEVELS = {"description-derived", "full-reviewed"}
ROLES = {"primary", "specialist", "alternate", "complementary", "standalone"}
BEHAVIOR_DIRS = {"references", "scripts", "agents"}
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".tmp"}

DIMENSIONS = {
    "fit": 25,
    "output": 25,
    "reliability": 15,
    "efficiency": 10,
    "maintainability": 10,
    "uniqueness": 10,
    "safety": 5,
}
SOURCE_WEIGHTS = {"agent": 1.0, "test": 1.5, "user": 2.0}
VERDICT_CAPS = {"pass": 100.0, "partial": 69.0, "fail": 49.0}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


@contextmanager
def locked_json(path: Path, default: dict, timeout: float = 5.0):
    lock = path.with_name(f".{path.name}.lock")
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 60:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Registry is busy: {path}")
            time.sleep(0.05)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        fd = None
        data = read_json(path, default)
        yield data
        data["updated_at"] = now_iso()
        write_json_atomic(path, data)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}
    lines = match.group(1).splitlines()
    result: dict[str, str] = {}
    index = 0
    while index < len(lines):
        field = re.match(r"^(name|description):\s*(.*)$", lines[index])
        if not field:
            index += 1
            continue
        key, value = field.group(1), field.group(2).strip()
        if value in {">", ">-", "|", "|-"}:
            block: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith(" ") or not lines[index].strip()):
                block.append(lines[index].strip())
                index += 1
            result[key] = " ".join(item for item in block if item)
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[key] = value
        index += 1
    return result


def behavior_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    skill_md = folder / "SKILL.md"
    if skill_md.is_file():
        files.append(skill_md)
    for directory in BEHAVIOR_DIRS:
        base = folder / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(folder)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if path.suffix.lower() in IGNORED_SUFFIXES:
                continue
            files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(folder).as_posix())


def behavior_fingerprint(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in behavior_files(folder):
        relative = path.relative_to(folder).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def route_fingerprint(route: dict) -> str:
    payload = json.dumps(route, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def version_key(value: str) -> tuple[int, ...]:
    numbers = [int(number) for number in re.findall(r"\d+", value)]
    return tuple(numbers) if numbers else (0,)


def discover_standard(root: Path, root_kind: str) -> list[dict]:
    found: list[dict] = []
    if not root.exists():
        return found
    for folder in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        skill_md = folder / "SKILL.md"
        if not folder.is_dir() or not skill_md.is_file():
            continue
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        name = meta.get("name") or folder.name
        found.append(
            {
                "key": name,
                "display_name": name,
                "path": str(folder.resolve()),
                "root_kind": root_kind,
                "fingerprint": behavior_fingerprint(folder),
            }
        )
    return found


def active_plugin_names(config_path: Path, roadmap: dict) -> set[str]:
    """Use mapped callable plugins, but always honor explicit disabled config entries."""
    mapped = {key.split(":", 1)[0] for key in roadmap if ":" in key}
    if not config_path.is_file():
        return mapped
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return mapped
    enabled: set[str] = set()
    disabled: set[str] = set()
    for identity, settings in config.get("plugins", {}).items():
        if not isinstance(settings, dict):
            continue
        name = identity.split("@", 1)[0]
        (enabled if settings.get("enabled", True) else disabled).add(name)
    return (mapped | enabled) - disabled


def discover_plugins(cache_root: Path, allowed_plugins: set[str]) -> list[dict]:
    if not cache_root.exists():
        return []
    latest: dict[str, tuple[tuple[int, ...], dict]] = {}
    for skill_md in cache_root.rglob("SKILL.md"):
        try:
            relative = skill_md.relative_to(cache_root)
        except ValueError:
            continue
        parts = relative.parts
        if "skills" not in parts:
            continue
        skill_index = parts.index("skills")
        if skill_index < 3 or skill_index + 3 != len(parts):
            continue
        marketplace, plugin_name, plugin_version = parts[0], parts[1], parts[2]
        if plugin_name not in allowed_plugins:
            continue
        folder = skill_md.parent
        meta = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        skill_name = meta.get("name") or folder.name
        key = f"{plugin_name}:{skill_name}"
        item = {
            "key": key,
            "display_name": skill_name,
            "path": str(folder.resolve()),
            "root_kind": "plugin",
            "plugin_name": plugin_name,
            "plugin_version": plugin_version,
            "plugin_marketplace": marketplace,
            "fingerprint": behavior_fingerprint(folder),
        }
        candidate = (version_key(plugin_version), item)
        if key not in latest or candidate[0] > latest[key][0]:
            latest[key] = candidate
    return [entry[1] for entry in sorted(latest.values(), key=lambda item: item[1]["key"])]


def validate_route(route: dict) -> list[str]:
    errors = [field for field in ROUTE_REQUIRED if not isinstance(route.get(field), str) or not route[field].strip()]
    review_level = route.get("review_level", "description-derived")
    if review_level not in REVIEW_LEVELS:
        errors.append("review_level")
    role = route.get("role", "standalone")
    if role not in ROLES:
        errors.append("role")
    overlap = route.get("overlap_group", [])
    if isinstance(overlap, str):
        overlap = [overlap]
    if not isinstance(overlap, list) or any(not isinstance(item, str) or not item.strip() for item in overlap):
        errors.append("overlap_group")
    return errors


def current_evaluations(record: dict) -> list[dict]:
    fingerprint = record.get("fingerprint")
    return [
        event
        for event in record.get("evaluations", [])
        if event.get("fingerprint") == fingerprint and event.get("task_id")
    ][-10:]


def compact_evaluations(record: dict, keep: int = 50) -> None:
    """Keep recent evidence detailed and retain an auditable summary of older rows."""
    evaluations = record.get("evaluations", [])
    if len(evaluations) <= keep:
        return
    older = evaluations[:-keep]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in older:
        grouped[str(event.get("fingerprint") or "unknown")].append(event)
    archive = record.setdefault("evaluation_archive", [])
    for fingerprint, events in sorted(grouped.items()):
        task_ids = sorted({str(event.get("task_id")) for event in events if event.get("task_id")})
        numerator = sum(float(event.get("score", 0)) * float(event.get("weight", 1.0)) for event in events)
        denominator = sum(float(event.get("weight", 1.0)) for event in events if "score" in event)
        summary = next((item for item in archive if item.get("fingerprint") == fingerprint), None)
        if summary is None:
            summary = {
                "fingerprint": fingerprint,
                "event_count": 0,
                "task_ids": [],
                "source_counts": {},
                "verdict_counts": {},
                "score_weighted_sum": 0.0,
                "score_weight_sum": 0.0,
                "first_timestamp": "",
                "last_timestamp": "",
            }
            archive.append(summary)
        summary["archived_at"] = now_iso()
        summary["event_count"] = int(summary.get("event_count", 0)) + len(events)
        summary["task_ids"] = sorted(set(summary.get("task_ids", [])) | set(task_ids))
        summary["task_count"] = len(summary["task_ids"])
        for field, values in (
            ("source_counts", Counter(str(event.get("source", "unknown")) for event in events)),
            ("verdict_counts", Counter(str(event.get("verdict", "unknown")) for event in events)),
        ):
            counts = Counter(summary.get(field, {}))
            counts.update(values)
            summary[field] = dict(counts)
        summary["score_weighted_sum"] = float(summary.get("score_weighted_sum", 0.0)) + numerator
        summary["score_weight_sum"] = float(summary.get("score_weight_sum", 0.0)) + denominator
        summary["weighted_score"] = round(
            summary["score_weighted_sum"] / summary["score_weight_sum"], 1
        ) if summary["score_weight_sum"] else 60.0
        timestamps = [str(event.get("timestamp", "")) for event in events if event.get("timestamp")]
        if timestamps:
            previous_first = str(summary.get("first_timestamp", ""))
            summary["first_timestamp"] = min([*timestamps, previous_first] if previous_first else timestamps)
            previous_last = str(summary.get("last_timestamp", ""))
            summary["last_timestamp"] = max([*timestamps, previous_last] if previous_last else timestamps)
    record["evaluation_archive"] = archive
    record["evaluations"] = evaluations[-keep:]


def weighted_score(evaluations: list[dict]) -> float:
    if not evaluations:
        return 60.0
    numerator = sum(float(item["score"]) * float(item.get("weight", 1.0)) for item in evaluations)
    denominator = sum(float(item.get("weight", 1.0)) for item in evaluations)
    return round(numerator / denominator, 1) if denominator else 60.0


def quality_state(record: dict) -> tuple[float, str, str, int]:
    root_kind = record.get("root_kind", "shared")
    if root_kind == "system":
        return 60.0, "system", "protected", 0
    if root_kind == "plugin":
        events = current_evaluations(record)
        return weighted_score(events), "plugin-managed", "protected", len({item["task_id"] for item in events})

    events = current_evaluations(record)
    score = weighted_score(events)
    task_count = len({item["task_id"] for item in events})
    external = any(item.get("source") in {"user", "test"} for item in events)
    user_evidence = any(item.get("source") == "user" for item in events)
    if any(int(item.get("safety", 5)) <= 1 for item in events):
        return score, "quarantine-candidate", "evidence-based", task_count
    if task_count < 3 or not external:
        return score, "probation", "provisional", task_count
    if task_count >= 5 and score >= 85 and user_evidence:
        return score, "preferred", "evidence-based", task_count
    if score >= 70:
        return score, "active", "evidence-based", task_count
    if score >= 55:
        return score, "watch", "evidence-based", task_count
    return score, "quarantine-candidate", "evidence-based", task_count


def command_scan(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    roadmap_data = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}})
    roadmap = roadmap_data.get("skills", {})
    discovered = discover_standard(Path(args.shared_root), "shared")
    discovered.extend(discover_standard(Path(args.system_root), "system"))
    if not args.no_plugins:
        allowed_plugins = active_plugin_names(Path(args.config), roadmap)
        discovered.extend(discover_plugins(Path(args.plugin_cache), allowed_plugins))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in discovered:
        grouped[item["key"]].append(item)
    priority = {"shared": 0, "system": 1, "plugin": 2}
    selected: dict[str, dict] = {}
    collisions: dict[str, list[str]] = {}
    for key, items in grouped.items():
        items.sort(key=lambda item: (priority.get(item["root_kind"], 9), item["path"]))
        selected[key] = items[0]
        unique_paths = sorted({item["path"] for item in items})
        if len(unique_paths) > 1:
            collisions[key] = unique_paths

    timestamp = now_iso()
    default_registry = {"schema_version": 2, "updated_at": None, "collisions": {}, "skills": {}}
    with locked_json(registry_path, default_registry) as data:
        previous_schema = int(data.get("schema_version", 1))
        data["schema_version"] = 2
        data["collisions"] = collisions
        existing = data.setdefault("skills", {})
        seen: set[str] = set()
        for key, item in selected.items():
            seen.add(key)
            record = existing.get(key, {})
            previous_skill_fp = record.get("mapping_skill_fingerprint") if previous_schema >= 2 else None
            previous_route_fp = record.get("mapping_route_fingerprint") if previous_schema >= 2 else None
            record.update({field: value for field, value in item.items() if field != "key"})
            for obsolete in ("route", "category", "description", "mapping_fingerprint"):
                record.pop(obsolete, None)
            record.setdefault("first_seen", timestamp)
            record["last_seen"] = timestamp
            record.setdefault("evaluations", [])
            legacy = [
                event
                for event in record["evaluations"]
                if not event.get("fingerprint") or not event.get("task_id")
            ]
            if legacy:
                record.setdefault("legacy_evaluations", []).extend(legacy)
                record["evaluations"] = [
                    event
                    for event in record["evaluations"]
                    if event.get("fingerprint") and event.get("task_id")
                ]
            compact_evaluations(record)

            route = roadmap.get(key)
            current_route_fp = route_fingerprint(route) if isinstance(route, dict) else None
            if key in collisions:
                record["mapping_status"] = "collision"
            elif not isinstance(route, dict) or validate_route(route):
                record["mapping_status"] = "unmapped"
            elif previous_skill_fp and (previous_skill_fp != record["fingerprint"] or previous_route_fp != current_route_fp):
                record["mapping_status"] = "stale"
            else:
                record["mapping_status"] = "current"
                record["mapping_skill_fingerprint"] = record["fingerprint"]
                record["mapping_route_fingerprint"] = current_route_fp
                record.setdefault("mapping_review_level", route.get("review_level", "description-derived"))
                record.setdefault("mapping_reviewed_at", route.get("reviewed_at", timestamp))

            old_status = record.get("status")
            score, status, confidence, task_count = quality_state(record)
            if old_status in {"disabled", "merged"} and item["root_kind"] == "shared":
                status = old_status
            record["score"] = score
            record["status"] = status
            record["confidence"] = confidence
            record["current_task_count"] = task_count
            existing[key] = record

        for key, record in existing.items():
            if key not in seen and record.get("status") not in {"merged", "disabled"}:
                record["status"] = "missing"

    states = Counter(
        read_json(registry_path, default_registry).get("skills", {}).get(key, {}).get("mapping_status", "unmapped")
        for key in seen
    )
    print(
        f"Scanned {len(seen)} skills; shared/system/plugin="
        f"{sum(1 for item in selected.values() if item['root_kind']=='shared')}/"
        f"{sum(1 for item in selected.values() if item['root_kind']=='system')}/"
        f"{sum(1 for item in selected.values() if item['root_kind']=='plugin')}; "
        f"current={states['current']}, stale={states['stale']}, unmapped={states['unmapped']}, collisions={len(collisions)}"
    )
    return 0


def command_record(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    default_registry = {"schema_version": 2, "updated_at": None, "collisions": {}, "skills": {}}
    with locked_json(registry_path, default_registry) as data:
        record = data.get("skills", {}).get(args.skill)
        if not record:
            print(f"Unknown skill: {args.skill}. Run scan after installation or update.", file=sys.stderr)
            return 2
        if record.get("status") == "missing":
            print(f"Skill is missing: {args.skill}", file=sys.stderr)
            return 2
        live_path = Path(str(record.get("path", "")))
        if not live_path.is_dir():
            print(f"Skill path is unavailable: {args.skill}. Run scan before recording evidence.", file=sys.stderr)
            return 2
        try:
            live_fingerprint = behavior_fingerprint(live_path)
        except OSError as error:
            print(f"Cannot fingerprint {args.skill}: {error}", file=sys.stderr)
            return 2
        if live_fingerprint != record.get("fingerprint"):
            print(f"Skill changed since the last scan: {args.skill}. Scan and acknowledge its roadmap first.", file=sys.stderr)
            return 2
        if not args.task_id.strip() or not args.evidence.strip():
            print("task-id and evidence must not be blank", file=sys.stderr)
            return 2
        duplicate = any(
            event.get("fingerprint") == record.get("fingerprint")
            and event.get("task_id") == args.task_id.strip()
            and event.get("source") == args.source
            for event in record.get("evaluations", [])
        )
        if duplicate:
            print("Evidence already exists for this skill version, task-id, and source.", file=sys.stderr)
            return 2
        ratings = {dimension: int(getattr(args, dimension)) for dimension in DIMENSIONS}
        raw_score = sum(ratings[name] * weight for name, weight in DIMENSIONS.items()) / 5.0
        score = min(raw_score, VERDICT_CAPS[args.verdict])
        event = {
            "timestamp": now_iso(),
            "task_id": args.task_id.strip(),
            "fingerprint": record.get("fingerprint"),
            "source": args.source,
            "weight": SOURCE_WEIGHTS[args.source],
            "verdict": args.verdict,
            "score": round(score, 1),
            **ratings,
            "evidence": args.evidence.strip(),
        }
        if args.artifact:
            event["artifact"] = args.artifact.strip()
        evaluations = record.setdefault("evaluations", [])
        evaluations.append(event)
        compact_evaluations(record)
        score, status, confidence, task_count = quality_state(record)
        record["score"] = score
        record["status"] = status
        record["confidence"] = confidence
        record["current_task_count"] = task_count
        result = (score, status, task_count, len(current_evaluations(record)))
    print(f"{args.skill}: {result[0]}/100, {result[1]}, tasks={result[2]}, current-evidence={result[3]}")
    return 0


def overlap_groups(route: dict) -> set[str]:
    value = route.get("overlap_group", [])
    if isinstance(value, str):
        return {value}
    return {item for item in value if isinstance(item, str) and item.strip()}


def duplicate_candidates(skills: dict, roadmap: dict, threshold: float) -> list[tuple[float, str, str, str]]:
    active = [
        (key, record)
        for key, record in skills.items()
        if record.get("status") not in {"missing", "disabled", "merged"}
    ]
    candidates: list[tuple[float, str, str, str]] = []
    for index, (left_key, left) in enumerate(active):
        for right_key, right in active[index + 1 :]:
            if left.get("path") == right.get("path"):
                continue
            if left.get("fingerprint") == right.get("fingerprint") and threshold <= 1.0:
                candidates.append((1.0, left_key, right_key, "exact-behavior"))
                continue
            left_route, right_route = roadmap.get(left_key, {}), roadmap.get(right_key, {})
            shared_groups = overlap_groups(left_route) & overlap_groups(right_route)
            if not shared_groups:
                continue
            left_role = left_route.get("role", "standalone")
            right_role = right_route.get("role", "standalone")
            if {left_role, right_role} & {"specialist", "complementary"}:
                continue
            candidate_roles = {"primary", "alternate"}
            is_candidate = "alternate" in {left_role, right_role} or (
                left_role in candidate_roles and right_role in candidate_roles
            )
            if is_candidate and threshold <= 0.85:
                reason = "overlap:" + ",".join(sorted(shared_groups))
                candidates.append((0.85, left_key, right_key, reason))
    return sorted(candidates, reverse=True)


def command_duplicates(args: argparse.Namespace) -> int:
    data = read_json(Path(args.registry), {"schema_version": 2, "skills": {}})
    skills = data.get("skills", {})
    roadmap = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}}).get("skills", {})
    candidates = duplicate_candidates(skills, roadmap, args.threshold)
    if not candidates:
        print("No duplicate candidates at this threshold.")
        return 0
    for score, left, right, reason in candidates:
        left_record, right_record = skills.get(left, {}), skills.get(right, {})
        left_route, right_route = roadmap.get(left, {}), roadmap.get(right, {})
        protected = any(record.get("root_kind") in {"system", "plugin"} for record in (left_record, right_record))
        different_runtime = left_record.get("root_kind") != right_record.get("root_kind")
        review = "boundary-review" if protected or different_runtime else "merge-review"
        print(
            f"{score:.2f}\t{review}\t{reason}\t{left}\t{right}\n"
            f"  left: lane={left_route.get('lane', '-')} role={left_route.get('role', 'standalone')} "
            f"runtime={left_record.get('root_kind', '-')} boundary={left_route.get('boundary', '-')}\n"
            f"  right: lane={right_route.get('lane', '-')} role={right_route.get('role', 'standalone')} "
            f"runtime={right_record.get('root_kind', '-')} boundary={right_route.get('boundary', '-')}"
        )
    return 0


def command_report(args: argparse.Namespace) -> int:
    data = read_json(Path(args.registry), {"schema_version": 2, "skills": {}})
    roadmap_data = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}})
    roadmap = roadmap_data.get("skills", {})
    query = args.query.lower().strip()
    lane_filter = args.lane.lower().strip()
    rows = []
    excluded_unready = 0
    for key, record in data.get("skills", {}).items():
        if record.get("status") in {"missing", "disabled", "merged"}:
            continue
        if not args.include_unready and record.get("mapping_status", "unmapped") != "current":
            excluded_unready += 1
            continue
        route = roadmap.get(key, {})
        haystack = " ".join(
            [key, route.get("lane", ""), route.get("stage", ""), route.get("brief", ""), route.get("use_when", ""), route.get("boundary", "")]
        ).lower()
        if query and query not in haystack:
            continue
        if lane_filter and lane_filter not in route.get("lane", "").lower():
            continue
        rows.append((route.get("lane", "未映射"), -float(record.get("score", 60)), key, record, route))
    rows.sort()
    print(f"Registry: {len(data.get('skills', {}))} records; updated {data.get('updated_at')}")
    if query or lane_filter:
        print(f"Matched routes: {len(rows)}")
    else:
        counts = Counter(route.get("lane", "未映射") for _, _, _, _, route in rows)
        print("Functional lanes: " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts)))
        if excluded_unready:
            print(f"Excluded unready candidates: {excluded_unready}; use --include-unready with --lane or --query for governance review.")
        return 0
    for _, _, key, record, route in rows:
        events = current_evaluations(record)
        task_count = len({event["task_id"] for event in events})
        review_level = record.get("mapping_review_level", route.get("review_level", "description-derived"))
        print(
            f"{key}\t{route.get('lane', '未映射')}\t{route.get('stage', '-')}\t"
            f"score={record.get('score', 60):.1f}\t{record.get('status')}\t"
            f"map={record.get('mapping_status', 'unmapped')}\treview={review_level}\ttasks={task_count}\n"
            f"  功能：{route.get('brief', '-')}\n  场景：{route.get('use_when', '-')}\n  边界：{route.get('boundary', '-')}"
        )
    return 0


def command_ack_map(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry)
    roadmap = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}}).get("skills", {})
    route = roadmap.get(args.skill)
    if not isinstance(route, dict) or validate_route(route):
        print(f"Roadmap entry is missing or invalid: {args.skill}", file=sys.stderr)
        return 2
    default_registry = {"schema_version": 2, "updated_at": None, "collisions": {}, "skills": {}}
    with locked_json(registry_path, default_registry) as data:
        record = data.get("skills", {}).get(args.skill)
        if not record:
            print(f"Unknown skill: {args.skill}. Run scan first.", file=sys.stderr)
            return 2
        record["mapping_skill_fingerprint"] = record.get("fingerprint")
        record["mapping_route_fingerprint"] = route_fingerprint(route)
        record["mapping_status"] = "current"
        record["mapping_review_level"] = args.review_level
        record["mapping_reviewed_at"] = now_iso()
    print(f"Roadmap acknowledged for {args.skill} as {args.review_level}.")
    return 0


def command_sources_report(args: argparse.Namespace) -> int:
    registry = read_json(Path(args.registry), {"schema_version": 2, "skills": {}}).get("skills", {})
    sources = read_json(Path(args.sources), {"schema_version": 1, "skills": {}}).get("skills", {})
    shared = {key for key, record in registry.items() if record.get("root_kind") == "shared" and record.get("status") != "missing"}
    tracked = sorted(shared & set(sources))
    untracked = sorted(shared - set(sources))
    print(f"Shared skills: {len(shared)}; tracked sources: {len(tracked)}; untracked: {len(untracked)}")
    if args.show_untracked:
        for key in untracked:
            print(f"untracked\t{key}")
    for key in tracked:
        source = sources[key]
        print(
            f"tracked\t{key}\t{source.get('kind', 'unknown')}\t{source.get('repo', '-')}\t"
            f"commit={source.get('installed_commit', '-') or '-'}\tlocal-mods={bool(source.get('local_modifications'))}"
        )
    return 0


def github_latest_commit(source: dict, timeout: float) -> str:
    repo = source["repo"]
    ref = source.get("ref", "main")
    params = {"sha": ref, "per_page": "1"}
    if source.get("path"):
        params["path"] = source["path"]
    url = f"https://api.github.com/repos/{repo}/commits?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "skill-router/2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("No commit returned")
    return str(payload[0]["sha"])


def command_check_updates(args: argparse.Namespace) -> int:
    sources = read_json(Path(args.sources), {"schema_version": 1, "skills": {}}).get("skills", {})
    keys = [args.skill] if args.skill else sorted(sources)

    def inspect(key: str) -> tuple[str, bool]:
        source = sources.get(key)
        if not source:
            return f"untracked\t{key}", True
        if source.get("kind") != "github" or not source.get("repo"):
            return f"unsupported\t{key}\t{source.get('kind', 'unknown')}", False
        installed = source.get("installed_commit")
        if not installed:
            return f"unpinned\t{key}\t{source['repo']}", False
        try:
            latest = github_latest_commit(source, args.timeout)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as error:
            return f"error\t{key}\t{error}", True
        status = "up-to-date" if latest == installed else "update-available"
        local_mods = " local-modifications" if source.get("local_modifications") else ""
        return f"{status}\t{key}\tinstalled={installed}\tlatest={latest}{local_mods}", False

    worker_count = min(max(1, int(args.workers)), 4, max(1, len(keys)))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = dict(zip(keys, pool.map(inspect, keys)))
    failures = 0
    for key in keys:
        line, failed = results[key]
        print(line)
        failures += int(failed)
    return 1 if failures else 0


def command_validate(args: argparse.Namespace) -> int:
    registry_data = read_json(Path(args.registry), {"schema_version": 2, "skills": {}})
    roadmap_data = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}})
    sources_data = read_json(Path(args.sources), {"schema_version": 1, "skills": {}})
    skills = registry_data.get("skills", {})
    roadmap = roadmap_data.get("skills", {})
    retirements = read_json(Path(args.registry).with_name("skill-retirements.json"), {"skills": {}}).get("skills", {})
    errors: list[str] = []
    warnings: list[str] = []
    target = args.skill.strip() if args.skill else ""

    if target and target not in set(skills) | set(roadmap):
        errors.append(f"unknown scoped skill: {target}")

    if int(registry_data.get("schema_version", 0)) != 2:
        errors.append("registry schema_version must be 2")
    if int(roadmap_data.get("schema_version", 0)) != 2:
        errors.append("roadmap schema_version must be 2")
    for key, route in roadmap.items():
        if target and key != target:
            continue
        fields = validate_route(route) if isinstance(route, dict) else list(ROUTE_REQUIRED)
        if fields:
            errors.append(f"invalid route {key}: {','.join(fields)}")
    active_all = {key for key, record in skills.items() if record.get("status") != "missing"}
    active = ({target} & active_all) if target else active_all
    for key in sorted(active & set(retirements)):
        if not retirements[key].get("reactivated_at"):
            errors.append(f"retired skill active in registry: {key}")
    for key in sorted(active - set(roadmap)):
        errors.append(f"unmapped active skill: {key}")
    roadmap_scope = ({target} & set(roadmap)) if target else set(roadmap)
    for key in sorted(roadmap_scope - set(skills)):
        warnings.append(f"roadmap entry without installed skill: {key}")
    for key, record in skills.items():
        if target and key != target:
            continue
        if "route" in record:
            errors.append(f"duplicated route data in registry: {key}")
        if record.get("mapping_status") in {"stale", "unmapped", "collision"} and record.get("status") != "missing":
            warnings.append(f"mapping {record.get('mapping_status')}: {key}")
        current = current_evaluations(record)
        if record.get("status") in {"active", "preferred"} and len({event["task_id"] for event in current}) < 3:
            errors.append(f"premature quality status: {key}")
    collisions = registry_data.get("collisions", {})
    if collisions and (not target or target in collisions):
        errors.append(f"name collisions: {1 if target else len(collisions)}")

    if args.live:
        discovered = discover_standard(Path(args.shared_root), "shared")
        discovered.extend(discover_standard(Path(args.system_root), "system"))
        if not args.no_plugins:
            allowed_plugins = active_plugin_names(Path(args.config), roadmap)
            discovered.extend(discover_plugins(Path(args.plugin_cache), allowed_plugins))
        live = {item["key"]: item for item in discovered}
        live_scope = ({target} & set(live)) if target else set(live)
        for key in sorted(live_scope & set(retirements)):
            if not retirements[key].get("reactivated_at"):
                errors.append(f"retired skill rediscovered: {key}")
        for key in sorted(live_scope - set(skills)):
            errors.append(f"live missing-registry: {key}")
        for key in sorted(active - set(live)):
            errors.append(f"live missing-skill: {key}")
        for key in sorted(active & set(live)):
            if live[key].get("fingerprint") != skills[key].get("fingerprint"):
                errors.append(f"live fingerprint-drift: {key}")
    invalid_events = sum(
        1
        for key, record in skills.items()
        if not target or key == target
        for event in record.get("evaluations", [])
        if not event.get("fingerprint") or not event.get("task_id")
    )
    if invalid_events:
        errors.append(f"unmigrated evidence in active evaluation sets: {invalid_events}")
    shared = {key for key, record in skills.items() if record.get("root_kind") == "shared" and record.get("status") != "missing"}
    source_keys = set(sources_data.get("skills", {}))
    source_scope = ({target} & shared) if target else shared
    if target:
        if target in shared and target not in source_keys:
            warnings.append(f"source metadata missing: {target}")
    else:
        warnings.append(f"source coverage: {len(shared & source_keys)}/{len(shared)} shared skills")
    for key in sorted(source_scope & source_keys):
        source = sources_data.get("skills", {}).get(key, {})
        if source.get("kind") == "github":
            missing = [field for field in ("repo", "ref", "installed_commit", "license") if not source.get(field)]
            if missing:
                warnings.append(f"source baseline incomplete: {key} ({','.join(missing)})")
        elif source.get("kind") == "local":
            missing = [field for field in ("license", "local_modifications") if not source.get(field)]
            if missing:
                warnings.append(f"local source metadata incomplete: {key} ({','.join(missing)})")

    duplicate_pairs = duplicate_candidates(skills, roadmap, 0.72)
    if target:
        duplicate_pairs = [item for item in duplicate_pairs if target in {item[1], item[2]}]
    duplicate_count = len(duplicate_pairs)
    if duplicate_count:
        warnings.append(f"duplicate candidates requiring review: {duplicate_count}")
    print(f"Validation: skills={len(skills)}, roadmap={len(roadmap)}, errors={len(errors)}, warnings={len(warnings)}")
    for item in errors:
        print(f"ERROR\t{item}")
    for item in warnings:
        print(f"WARN\t{item}")
    return 1 if errors or (args.strict and warnings) else 0


def command_package_check(args: argparse.Namespace) -> int:
    """Validate distributable skills against the roadmap without machine state."""
    package_root = Path(args.package_root).resolve()
    roadmap_data = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}})
    roadmap = roadmap_data.get("skills", {})
    errors: list[str] = []
    discovered = discover_standard(package_root, "package")
    by_key: dict[str, list[dict]] = defaultdict(list)
    for item in discovered:
        by_key[item["key"]].append(item)
    for key, items in sorted(by_key.items()):
        if len(items) > 1:
            errors.append(f"duplicate packaged skill name: {key}")
    for key in sorted(set(roadmap) - set(by_key)):
        errors.append(f"roadmap entry without packaged skill: {key}")
    for key in sorted(set(by_key) - set(roadmap)):
        errors.append(f"packaged skill without roadmap entry: {key}")
    for key, route in roadmap.items():
        fields = validate_route(route) if isinstance(route, dict) else list(ROUTE_REQUIRED)
        if fields:
            errors.append(f"invalid route {key}: {','.join(fields)}")
    print(f"Package validation: skills={len(discovered)} roadmap={len(roadmap)} errors={len(errors)}")
    for error in errors:
        print(f"ERROR\t{error}")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--roadmap", default=str(DEFAULT_ROADMAP))
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="scan shared, system, and plugin skill roots")
    scan.add_argument("--shared-root", default=str(DEFAULT_SHARED_ROOT))
    scan.add_argument("--system-root", default=str(DEFAULT_SYSTEM_ROOT))
    scan.add_argument("--plugin-cache", default=str(DEFAULT_PLUGIN_CACHE))
    scan.add_argument("--config", default=str(DEFAULT_CODEX_CONFIG))
    scan.add_argument("--no-plugins", action="store_true")
    scan.set_defaults(func=command_scan)

    report = subparsers.add_parser("report", help="show functional routes and current-version quality")
    report.add_argument("--query", default="", help="literal maintenance filter; normal routing should select a semantic lane first")
    report.add_argument("--lane", default="")
    report.add_argument("--include-unready", action="store_true", help="include stale, unmapped, or colliding candidates for governance review")
    report.set_defaults(func=command_report)

    duplicates = subparsers.add_parser("duplicates", help="list exact or declared-overlap candidates")
    duplicates.add_argument("--threshold", type=float, default=0.72)
    duplicates.set_defaults(func=command_duplicates)

    record = subparsers.add_parser("record-outcome", help="append version-bound evidence")
    record.add_argument("--skill", required=True)
    record.add_argument("--task-id", required=True)
    record.add_argument("--verdict", choices=sorted(VERDICT_CAPS), required=True)
    record.add_argument("--source", choices=sorted(SOURCE_WEIGHTS), default="agent")
    for dimension in DIMENSIONS:
        record.add_argument(f"--{dimension}", type=int, choices=range(1, 6), required=True)
    record.add_argument("--evidence", required=True)
    record.add_argument("--artifact")
    record.set_defaults(func=command_record)

    acknowledge = subparsers.add_parser("ack-map", help="confirm roadmap against the current behavior fingerprint")
    acknowledge.add_argument("--skill", required=True)
    acknowledge.add_argument("--review-level", choices=sorted(REVIEW_LEVELS), required=True)
    acknowledge.set_defaults(func=command_ack_map)

    sources = subparsers.add_parser("sources-report", help="show source metadata coverage")
    sources.add_argument("--show-untracked", action="store_true")
    sources.set_defaults(func=command_sources_report)

    updates = subparsers.add_parser("check-updates", help="read-only GitHub update check for tracked skills")
    updates.add_argument("--skill")
    updates.add_argument("--timeout", type=float, default=10.0)
    updates.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    updates.set_defaults(func=command_check_updates)

    validate = subparsers.add_parser("validate", help="validate registry, roadmap, evidence, and overlap invariants")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--skill", default="", help="validate one changed skill without unrelated portfolio warnings")
    validate.add_argument("--live", action="store_true", help="compare registry fingerprints with installed skills")
    validate.add_argument("--shared-root", default=str(DEFAULT_SHARED_ROOT))
    validate.add_argument("--system-root", default=str(DEFAULT_SYSTEM_ROOT))
    validate.add_argument("--plugin-cache", default=str(DEFAULT_PLUGIN_CACHE))
    validate.add_argument("--config", default=str(DEFAULT_CODEX_CONFIG))
    validate.add_argument("--no-plugins", action="store_true")
    validate.set_defaults(func=command_validate)

    package_check = subparsers.add_parser(
        "package-check", help="validate packaged skills against the roadmap without installed registry state"
    )
    package_check.add_argument("--package-root", default=str(HERE.parents[1]))
    package_check.set_defaults(func=command_package_check)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
