#!/usr/bin/env python3
"""Evidence-aware skill usage ledger and portfolio audit."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skill_registry import (
    DEFAULT_REGISTRY,
    DEFAULT_ROADMAP,
    DEFAULT_SOURCES,
    duplicate_candidates,
    locked_json,
    now_iso,
    parse_frontmatter,
    read_json,
)


HERE = Path(__file__).resolve().parent
DEFAULT_USAGE = HERE.parent / "registry" / "skill-usage.json"
DEFAULT_RETIREMENTS = HERE.parent / "registry" / "skill-retirements.json"
USAGE_RESULTS = {"completed", "partial", "failed", "fallback"}
PROTECTED_ROOTS = {"system", "plugin"}
LINK_RE = re.compile(r"\]\((?!https?://|#)([^)]+)\)")
TODO_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?(?:TODO|FIXME)(?:\s*:|\s*$|\s*\[)")
ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "metadata", "allowed-tools"}


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def command_record_use(args: argparse.Namespace) -> int:
    registry = read_json(Path(args.registry), {"schema_version": 2, "skills": {}}).get("skills", {})
    record = registry.get(args.skill)
    if not record or record.get("status") == "missing":
        print(f"Unknown active skill: {args.skill}")
        return 2
    if record.get("mapping_status") != "current":
        print(f"Refusing usage evidence for unready skill: {args.skill} ({record.get('mapping_status', 'unmapped')})")
        return 2
    default = {"schema_version": 1, "updated_at": None, "skills": {}}
    with locked_json(Path(args.usage), default) as data:
        skill = data.setdefault("skills", {}).setdefault(args.skill, {"events": [], "archive": {}})
        events = skill.setdefault("events", [])
        duplicate = next(
            (
                event
                for event in events
                if event.get("task_id") == args.task_id and event.get("fingerprint") == record.get("fingerprint")
            ),
            None,
        )
        if duplicate:
            print(f"Usage already recorded for {args.skill} task {args.task_id}.")
            return 2
        event = {
            "timestamp": now_iso(),
            "task_id": args.task_id,
            "fingerprint": record.get("fingerprint"),
            "result": args.result,
            "reason": args.reason,
        }
        if args.artifact:
            event["artifact"] = args.artifact
        events.append(event)
        if len(events) > 200:
            removed = events[:-200]
            skill["events"] = events[-200:]
            archive = skill.setdefault("archive", {})
            archive["count"] = int(archive.get("count", 0)) + len(removed)
            result_counts = Counter(item.get("result", "unknown") for item in removed)
            merged = Counter(archive.get("results", {}))
            merged.update(result_counts)
            archive["results"] = dict(sorted(merged.items()))
    print(f"Recorded {args.result} use for {args.skill} task {args.task_id}.")
    return 0


def inspect_files(record: dict) -> dict:
    root = Path(record.get("path", ""))
    skill_file = root / "SKILL.md"
    result = {
        "skill_exists": skill_file.is_file(),
        "entry_characters": 0,
        "behavior_files": 0,
        "script_files": 0,
        "broken_links": [],
        "todo": False,
        "frontmatter_valid": False,
        "unsupported_frontmatter": [],
    }
    if not skill_file.is_file():
        return result
    text = skill_file.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(text)
    result["entry_characters"] = len(text)
    result["todo"] = bool(TODO_RE.search(text))
    result["frontmatter_valid"] = bool(frontmatter.get("name") and frontmatter.get("description"))
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if match:
        top_keys = {
            key
            for line in match.group(1).splitlines()
            if (key_match := re.match(r"^([A-Za-z0-9_-]+):", line))
            for key in [key_match.group(1)]
        }
        result["unsupported_frontmatter"] = sorted(top_keys - ALLOWED_FRONTMATTER_KEYS)
    files = [path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    result["behavior_files"] = len(files)
    result["script_files"] = sum(1 for path in files if "scripts" in path.parts and path.suffix.lower() in {".py", ".ps1", ".sh", ".js", ".ts"})
    broken: set[str] = set()
    for path in files:
        if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for link in LINK_RE.findall(body):
            clean = link.split("#", 1)[0].strip()
            if (
                not clean
                or clean.lower() in {"url", "path", "file"}
                or "<" in clean
                or ">" in clean
                or clean.startswith(("mailto:", "data:", "/"))
            ):
                continue
            target = (path.parent / clean).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                # Sibling-skill links are optional portfolio dependencies, not broken internal references.
                continue
            if not target.exists():
                broken.add(str(path.relative_to(root)) + " -> " + clean)
    result["broken_links"] = sorted(broken)
    return result


def usage_summary(name: str, fingerprint: str, usage: dict, days: int) -> dict:
    events = usage.get("skills", {}).get(name, {}).get("events", [])
    cutoff = datetime.now(timezone.utc).astimezone() - timedelta(days=days)
    recent = [event for event in events if (parse_time(event.get("timestamp", "")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]
    current = [event for event in recent if event.get("fingerprint") == fingerprint]
    counts = Counter(event.get("result", "unknown") for event in current)
    return {
        "recent_events": len(recent),
        "current_events": len(current),
        "completed": counts.get("completed", 0),
        "partial": counts.get("partial", 0),
        "failed": counts.get("failed", 0),
        "fallback": counts.get("fallback", 0),
        "last_used": max((event.get("timestamp", "") for event in recent), default=""),
    }


def readiness_score(record: dict, route: dict, source: dict | None, files: dict, is_overlap: bool) -> tuple[int, list[str]]:
    score = 100
    flags: list[str] = []
    if record.get("mapping_status") != "current":
        score -= 35
        flags.append("mapping-unready")
    if not files["skill_exists"] or not files["frontmatter_valid"]:
        score -= 35
        flags.append("invalid-entry")
    if files["unsupported_frontmatter"]:
        score -= 5
        flags.append("unsupported-frontmatter")
    if files["todo"]:
        score -= 30
        flags.append("unfinished-placeholder")
    if files["broken_links"]:
        score -= 30
        flags.append("broken-reference")
    if route.get("review_level", "description-derived") != "full-reviewed":
        score -= 5
        flags.append("description-only-map")
    if record.get("root_kind") == "shared":
        if source is None:
            score -= 10
            flags.append("source-untracked")
        elif not source.get("license") or source.get("license") == "unknown":
            score -= 8
            flags.append("license-unknown")
    if is_overlap:
        score -= 10
        flags.append("overlap-review")
    if files["script_files"]:
        flags.append("scripts-require-review")
    if files["entry_characters"] > 8000:
        score -= 5
        flags.append("large-entry")
    return max(0, score), flags


def portfolio_action(record: dict, route: dict, files: dict, overlap: bool, usage: dict) -> str:
    if record.get("root_kind") in PROTECTED_ROOTS:
        return "protected"
    if (
        record.get("mapping_status") != "current"
        or not files["frontmatter_valid"]
        or files["todo"]
        or files["broken_links"]
    ):
        return "repair"
    if files["unsupported_frontmatter"]:
        return "compatibility-review"
    if record.get("status") == "quarantine-candidate":
        return "quarantine-review"
    if overlap:
        return "compare"
    role = route.get("role", "standalone")
    if role in {"specialist", "complementary"}:
        return "keep-specialist"
    if record.get("status") in {"preferred", "active"}:
        return "keep-core"
    if role == "primary" and route.get("review_level") == "full-reviewed":
        return "keep-core-probation"
    if usage["completed"] or usage["partial"]:
        return "observe"
    return "trial-review"


def markdown_report(report: dict) -> str:
    lines = [
        "# Skill 组合专业评估",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "## 结论边界",
        "",
        "本报告将静态治理就绪度、版本质量证据和近期使用频率分开，不用文件长度或单次自评冒充专业质量。`trial-review` 只代表证据不足，不等于低质量；任何合并、停用或归档都必须经过同题 A/B、独特能力核对、授权检查和用户批准。",
        "",
        "## 组合概览",
        "",
        f"- 总记录：{report['summary']['total']}；共享：{report['summary']['shared']}；系统：{report['summary']['system']}；插件：{report['summary']['plugin']}。",
        f"- 已退出活动库且可恢复：{report['summary']['retired']}。",
        f"- 当前路标：{report['summary']['current']}；待修复：{report['summary']['unready']}；重复对比组：{report['summary']['overlap_pairs']}。",
        f"- 有当前版本质量证据：{report['summary']['any_evidence']}；达到至少 3 个不同任务的成熟证据：{report['summary']['evidence_mature']}；近期有使用记录：{report['summary']['recently_used']}。",
        "",
        "### 建议动作统计",
        "",
        "| 动作 | 数量 |",
        "|---|---:|",
    ]
    for key, count in sorted(report["action_counts"].items()):
        lines.append(f"| `{key}` | {count} |")
    lines.extend(["", "## 按功能域", "", "| 功能域 | 数量 |", "|---|---:|"])
    for lane, count in sorted(report["lane_counts"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {lane} | {count} |")
    lines.extend([
        "",
        "## 重叠对比组",
        "",
        "| 关系 | 左侧 | 右侧 | 推荐动作 |",
        "|---|---|---|---|",
    ])
    for item in report["overlaps"]:
        lines.append(f"| {item['reason']} | `{item['left']}` | `{item['right']}` | 同题 A/B 后决定主次、整合或保留边界 |")
    if not report["overlaps"]:
        lines.append("| 无 | - | - | - |")
    lines.extend(["", "## 已退役且可恢复", "", "| Skill | 替代者 | 归档位置 |", "|---|---|---|"])
    for name, item in sorted(report["retirements"].items()):
        lines.append(f"| `{name}` | `{item.get('replacement', '-')}` | `{item.get('archive_path', '-')}` |")
    if not report["retirements"]:
        lines.append("| 无 | - | - |")
    lines.extend([
        "",
        "## 全量初筛",
        "",
        "| Skill | 运行域 | 功能域 | 角色 | 就绪度 | 证据分 | 当前任务 | 近期使用 | 建议 | 风险标记 |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|",
    ])
    for item in report["skills"]:
        flags = ", ".join(item["flags"]) or "-"
        lines.append(
            f"| `{item['name']}` | {item['root_kind']} | {item['lane']} | {item['role']} | "
            f"{item['readiness_score']} | {item['quality_score']:.1f} | {item['quality_tasks']} | "
            f"{item['usage']['recent_events']} | `{item['action']}` | {flags} |"
        )
    lines.extend([
        "",
        "## 淘汰门禁",
        "",
        "只有同时满足以下条件才可进入建议停用：存在已验证替代者；独特能力已核对并迁移或确认无价值；同题 A/B 不劣于原技能；近期使用和用户依赖已检查；许可证允许整合；已建立可恢复备份。此报告不会自动移动或删除任何 Skill。",
        "",
    ])
    return "\n".join(lines)


def command_audit(args: argparse.Namespace) -> int:
    registry_data = read_json(Path(args.registry), {"schema_version": 2, "skills": {}})
    roadmap = read_json(Path(args.roadmap), {"schema_version": 2, "skills": {}}).get("skills", {})
    sources = read_json(Path(args.sources), {"schema_version": 1, "skills": {}}).get("skills", {})
    usage_data = read_json(Path(args.usage), {"schema_version": 1, "skills": {}})
    retirement_data = read_json(Path(args.retirements), {"schema_version": 1, "skills": {}})
    retirements = retirement_data.get("skills", {})
    records = {
        key: value
        for key, value in registry_data.get("skills", {}).items()
        if value.get("status") not in {"missing", "disabled", "merged"}
    }
    overlaps_raw = duplicate_candidates(records, roadmap, args.overlap_threshold)
    overlap_names = {name for _, left, right, _ in overlaps_raw for name in (left, right)}
    skills = []
    for name, record in sorted(records.items()):
        route = roadmap.get(name, {})
        files = inspect_files(record)
        recent = usage_summary(name, record.get("fingerprint", ""), usage_data, args.days)
        readiness, flags = readiness_score(record, route, sources.get(name), files, name in overlap_names)
        evaluations = [
            event
            for event in record.get("evaluations", [])
            if event.get("fingerprint") == record.get("fingerprint") and event.get("task_id")
        ]
        skills.append(
            {
                "name": name,
                "root_kind": record.get("root_kind", "unknown"),
                "lane": route.get("lane", "未映射"),
                "stage": route.get("stage", ""),
                "role": route.get("role", "standalone"),
                "mapping_status": record.get("mapping_status", "unmapped"),
                "review_level": record.get("mapping_review_level", route.get("review_level", "description-derived")),
                "quality_score": float(record.get("score", 60)),
                "quality_status": record.get("status", "probation"),
                "quality_tasks": len({event["task_id"] for event in evaluations}),
                "readiness_score": readiness,
                "flags": flags,
                "usage": recent,
                "action": portfolio_action(record, route, files, name in overlap_names, recent),
                "files": files,
                "source": sources.get(name),
            }
        )
    action_counts = Counter(item["action"] for item in skills)
    lane_counts = Counter(item["lane"] for item in skills)
    root_counts = Counter(item["root_kind"] for item in skills)
    report = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "window_days": args.days,
        "summary": {
            "total": len(skills),
            "shared": root_counts.get("shared", 0),
            "system": root_counts.get("system", 0),
            "plugin": root_counts.get("plugin", 0),
            "current": sum(item["mapping_status"] == "current" for item in skills),
            "unready": sum(item["mapping_status"] != "current" for item in skills),
            "overlap_pairs": len(overlaps_raw),
            "any_evidence": sum(item["quality_tasks"] > 0 for item in skills),
            "evidence_mature": sum(item["quality_tasks"] >= 3 for item in skills),
            "recently_used": sum(item["usage"]["recent_events"] > 0 for item in skills),
            "retired": len(retirements),
        },
        "action_counts": dict(sorted(action_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "overlaps": [
            {"score": score, "left": left, "right": right, "reason": reason}
            for score, left, right, reason in overlaps_raw
        ],
        "retirements": retirements,
        "skills": skills,
    }
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        path = Path(args.output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown_report(report), encoding="utf-8")
    print(
        f"Audited {len(skills)} skills; current={report['summary']['current']}; "
        f"unready={report['summary']['unready']}; overlaps={len(overlaps_raw)}; "
        f"recently-used={report['summary']['recently_used']}"
    )
    print("Actions: " + ", ".join(f"{key}={action_counts[key]}" for key in sorted(action_counts)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--roadmap", default=str(DEFAULT_ROADMAP))
    parser.add_argument("--sources", default=str(DEFAULT_SOURCES))
    parser.add_argument("--usage", default=str(DEFAULT_USAGE))
    parser.add_argument("--retirements", default=str(DEFAULT_RETIREMENTS))
    subparsers = parser.add_subparsers(dest="command", required=True)

    use = subparsers.add_parser("record-use", help="record one material skill use without changing quality score")
    use.add_argument("--skill", required=True)
    use.add_argument("--task-id", required=True)
    use.add_argument("--result", choices=sorted(USAGE_RESULTS), required=True)
    use.add_argument("--reason", required=True)
    use.add_argument("--artifact")
    use.set_defaults(func=command_record_use)

    audit = subparsers.add_parser("audit", help="create an evidence-aware portfolio audit")
    audit.add_argument("--days", type=int, default=180)
    audit.add_argument("--overlap-threshold", type=float, default=0.72)
    audit.add_argument("--output-json")
    audit.add_argument("--output-md")
    audit.set_defaults(func=command_audit)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
