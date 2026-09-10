#!/usr/bin/env python3
"""Create auditable capability routing, discovery and candidate-adoption artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ADOPTION_MODES = {"full_install", "reference_strengthen", "reject"}
LICENSE_STATES = {"compatible", "unknown", "incompatible"}
SAFETY_STATES = {"pass", "unknown", "fail"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists() and default is not None:
        return json.loads(json.dumps(default))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, payload: dict) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def string_list(value: object, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{field} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    return [item.strip() for item in value]


def validate_request(payload: dict) -> dict:
    required_strings = ("request_id", "deliverable", "lane", "stage")
    for field in required_strings:
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise ValueError(f"capability request requires {field}")
    for field in (
        "input_types",
        "target_tools",
        "constraints",
        "acceptance",
        "permissions",
    ):
        string_list(
            payload.get(field, []), field, allow_empty=field not in {"acceptance"}
        )
    provided = payload.get("provided_candidate")
    if provided is not None:
        if (
            not isinstance(provided, dict)
            or not str(provided.get("identifier", "")).strip()
        ):
            raise ValueError("provided_candidate requires identifier")
    if payload.get("reusability", "repeatable") not in {"one-off", "repeatable"}:
        raise ValueError("reusability must be one-off or repeatable")
    if not isinstance(payload.get("non_obvious_risk", False), bool):
        raise ValueError("non_obvious_risk must be boolean")
    return payload


def request_fingerprint(request: dict) -> str:
    fields = {
        key: request.get(key)
        for key in (
            "deliverable",
            "lane",
            "stage",
            "input_types",
            "target_tools",
            "constraints",
            "acceptance",
            "permissions",
            "reusability",
            "non_obvious_risk",
            "provided_candidate",
        )
    }
    encoded = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def object_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def intersects(requested: list[str], declared: list[str]) -> bool:
    if not requested or not declared:
        return True
    requested_folded = {item.casefold() for item in requested}
    declared_folded = {item.casefold() for item in declared}
    return bool(requested_folded & declared_folded) or "any" in declared_folded


def score_route(
    request: dict, route: dict, record: dict | None
) -> tuple[int, list[str], bool]:
    evidence: list[str] = []
    if str(route.get("lane", "")).casefold() != request["lane"].casefold():
        return 0, ["lane mismatch"], False
    score = 35
    evidence.append("semantic lane matches")
    if str(route.get("stage", "")).casefold() == request["stage"].casefold():
        score += 15
        evidence.append("stage matches")
    else:
        score += 7
        evidence.append("same lane, different stage; boundary review required")

    route_inputs = string_list(route.get("input_types", []), "route.input_types")
    route_tools = string_list(route.get("target_tools", []), "route.target_tools")
    request_inputs = string_list(request.get("input_types", []), "request.input_types")
    request_tools = string_list(request.get("target_tools", []), "request.target_tools")
    if not intersects(request_inputs, route_inputs):
        return score, evidence + ["declared input types are incompatible"], False
    if not intersects(request_tools, route_tools):
        return score, evidence + ["declared tools are incompatible"], False
    score += 10 if request_inputs and route_inputs else 5
    score += 10 if request_tools and route_tools else 5
    evidence.append("input and tool hard gates pass")

    if record is None:
        return (
            score,
            evidence
            + ["skill is not present in the installed registry; scan locally first"],
            False,
        )
    mapping_status = record.get("mapping_status")
    if mapping_status in {"stale", "unmapped", "collision"}:
        return score, evidence + [f"mapping is {mapping_status}"], False
    if mapping_status == "current":
        score += 15
        evidence.append("installed mapping is current")
    else:
        return score, evidence + ["installed mapping is not current"], False
    if route.get("review_level") == "full-reviewed":
        score += 10
    if route.get("role", "standalone") in {"primary", "specialist", "complementary"}:
        score += 5
    return min(score, 100), evidence, True


def local_candidates(request: dict, roadmap: dict, registry: dict) -> list[dict]:
    routes = roadmap.get("skills", {})
    records = registry.get("skills", {})
    candidates: list[dict] = []
    for name, route in routes.items():
        if not isinstance(route, dict):
            continue
        score, evidence, eligible = score_route(request, route, records.get(name))
        if not score:
            continue
        candidates.append(
            {
                "name": name,
                "score": score,
                "eligible": eligible,
                "role": route.get("role", "standalone"),
                "boundary": route.get("boundary"),
                "overlap_group": route.get("overlap_group", []),
                "behavior_fingerprint": records.get(name, {}).get("fingerprint"),
                "mapping_route_fingerprint": records.get(name, {}).get(
                    "mapping_route_fingerprint"
                ),
                "evidence": evidence,
            }
        )
    return sorted(
        candidates,
        key=lambda item: (item["eligible"], item["score"], item["name"]),
        reverse=True,
    )[:5]


def command_assess(args: argparse.Namespace) -> int:
    request = validate_request(read_json(Path(args.request)))
    roadmap = read_json(Path(args.roadmap), {"skills": {}})
    registry = read_json(Path(args.registry), {"skills": {}})
    candidates = local_candidates(request, roadmap, registry)
    registry_state = "ready" if registry.get("skills") else "uninitialized"
    eligible = [item for item in candidates if item["eligible"]]
    best = eligible[0] if eligible else None
    result = (
        "fit"
        if best and best["score"] >= 75
        else "partial"
        if best and best["score"] >= 55
        else "gap"
    )
    provided = request.get("provided_candidate")
    next_state = (
        "local_scan"
        if registry_state == "uninitialized"
        else "candidate_review"
        if provided
        else "complete"
        if result == "fit"
        else "online_search"
    )
    cache_key = object_fingerprint(
        {
            "request": request_fingerprint(request),
            "result": result,
            "candidates": [
                {
                    "name": item["name"],
                    "eligible": item["eligible"],
                    "score": item["score"],
                    "behavior_fingerprint": item["behavior_fingerprint"],
                    "mapping_route_fingerprint": item["mapping_route_fingerprint"],
                }
                for item in candidates
            ],
        }
    )
    payload = {
        "schema_version": 1,
        "artifact": "routing-decision",
        "request_id": request["request_id"],
        "request_fingerprint": request_fingerprint(request),
        "cache_key": cache_key,
        "created_at": now_iso(),
        "result": result,
        "registry_state": registry_state,
        "selected_primary": best["name"] if result == "fit" and best else None,
        "local_candidates": candidates,
        "provided_candidate": provided,
        "online_search_required": registry_state == "ready"
        and not provided
        and result != "fit",
        "next_state": next_state,
        "decision_rule": (
            "task fit before historical quality; ineligible mappings never win"
        ),
    }
    output_path = Path(args.output)
    if output_path.exists() and read_json(output_path).get("cache_key") == cache_key:
        print(f"Routing decision reused: {result}; candidates={len(candidates)}")
        return 0
    write_json(output_path, payload)
    print(
        f"Routing decision: {result}; next={next_state}; candidates={len(candidates)}"
    )
    return 0


def github_search(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {"q": query, "sort": "updated", "order": "desc", "per_page": limit}
    )
    request = urllib.request.Request(
        "https://api.github.com/search/repositories?" + params,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-creation-workflow-skill-governor/1",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("items", []), list):
        raise ValueError("GitHub search returned an unexpected payload")
    results: list[dict] = []
    for item in payload.get("items", [])[:limit]:
        license_row = item.get("license") or {}
        results.append(
            {
                "identifier": item.get("full_name"),
                "url": item.get("html_url"),
                "description": item.get("description"),
                "updated_at": item.get("updated_at"),
                "stars": item.get("stargazers_count"),
                "license": license_row.get("spdx_id"),
                "source": "manager-online-search",
                "trust": "untrusted-until-reviewed",
            }
        )
    return results


def command_resolve(args: argparse.Namespace) -> int:
    request = validate_request(read_json(Path(args.request)))
    decision = read_json(Path(args.decision))
    if decision.get("request_fingerprint") != request_fingerprint(request):
        raise ValueError(
            "routing decision does not match the current capability request"
        )
    output_path = Path(args.output)
    if output_path.exists():
        existing = read_json(output_path)
        if (
            existing.get("request_fingerprint") == request_fingerprint(request)
            and existing.get("routing_cache_key") == decision.get("cache_key")
            and existing.get("status") != "online_search_failed"
        ):
            print(
                f"Gap resolution reused: {existing.get('status')}; "
                f"next={existing.get('next_action')}"
            )
            return 0
    provided = request.get("provided_candidate")
    online_results: list[dict] = []
    search_status = "skipped"
    error_text = None
    gap_action = None
    if decision.get("registry_state") == "uninitialized":
        status = "local_scan_required"
        next_action = "run-skill-registry-scan"
        candidate_source = None
    elif provided:
        status = "candidate_review"
        next_action = "audit-provided-candidate"
        candidate_source = "user-provided"
    elif decision.get("result") == "fit" and args.online != "always":
        status = "not_needed"
        next_action = "use-local-route"
        candidate_source = None
    elif args.online == "never":
        gap_action = args.gap_action or (
            "improve"
            if decision.get("result") == "partial"
            else "create"
            if request.get("reusability", "repeatable") == "repeatable"
            or request.get("non_obvious_risk", False)
            else "use-tool"
        )
        status = "resolution_ready"
        next_action = f"stage-{gap_action}"
        candidate_source = None
    else:
        terms = string_list(request.get("search_terms", []), "search_terms")
        query = " ".join(
            terms or [request["lane"], request["deliverable"], "SKILL.md agent skill"]
        )
        try:
            online_results = github_search(query, args.limit)
            search_status = "completed"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            search_status = "failed"
            error_text = str(error)
        if search_status == "failed":
            status = "online_search_failed"
            next_action = "retry-search-or-request-direction"
        elif online_results:
            status = "candidate_review"
            next_action = "audit-online-candidates"
        else:
            gap_action = args.gap_action or (
                "improve"
                if decision.get("result") == "partial"
                else "create"
                if request.get("reusability", "repeatable") == "repeatable"
                or request.get("non_obvious_risk", False)
                else "use-tool"
            )
            status = "resolution_ready"
            next_action = f"stage-{gap_action}"
        candidate_source = "manager-online-search" if online_results else None
    payload = {
        "schema_version": 1,
        "artifact": "gap-resolution",
        "request_id": request["request_id"],
        "request_fingerprint": request_fingerprint(request),
        "routing_cache_key": decision.get("cache_key"),
        "created_at": now_iso(),
        "status": status,
        "local_candidates": decision.get("local_candidates", []),
        "provided_candidate": provided,
        "candidate_source": candidate_source,
        "online_search": {
            "status": search_status,
            "results": online_results,
            "error": error_text,
        },
        "gap_spec": {
            "deliverable": request["deliverable"],
            "lane": request["lane"],
            "stage": request["stage"],
            "input_types": request.get("input_types", []),
            "target_tools": request.get("target_tools", []),
            "constraints": request.get("constraints", []),
            "acceptance": request.get("acceptance", []),
            "permissions": request.get("permissions", []),
            "reusability": request.get("reusability", "repeatable"),
            "non_obvious_risk": request.get("non_obvious_risk", False),
        }
        if gap_action
        else None,
        "gap_action": gap_action,
        "next_action": next_action,
        "resume_from": str(Path(args.output).resolve()),
    }
    write_json(output_path, payload)
    print(f"Gap resolution: {status}; next={next_action}; online={search_status}")
    return 2 if search_status == "failed" else 0


def validate_candidate_review(payload: dict) -> dict:
    candidate = payload.get("candidate")
    review = payload.get("review")
    if (
        not isinstance(candidate, dict)
        or not str(candidate.get("identifier", "")).strip()
    ):
        raise ValueError("candidate review requires candidate.identifier")
    if candidate.get("source") not in {
        "user-provided",
        "manager-online-search",
        "local",
    }:
        raise ValueError(
            "candidate.source must identify user, manager search, or local origin"
        )
    string_list(payload.get("overlap_findings", []), "overlap_findings")
    for field in ("candidate_behavior_fingerprint", "existing_behavior_fingerprint"):
        if payload.get(field) is not None and (
            not isinstance(payload[field], str) or not payload[field].strip()
        ):
            raise ValueError(f"{field} must be null or a non-empty string")
    if not isinstance(review, dict):
        raise ValueError("candidate review requires review object")
    overlap = review.get("overlap_score")
    if not isinstance(overlap, (int, float)) or not 0 <= overlap <= 1:
        raise ValueError("review.overlap_score must be between 0 and 1")
    string_list(review.get("unique_gain", []), "review.unique_gain")
    if not isinstance(review.get("independent_boundary"), bool):
        raise ValueError("review.independent_boundary must be boolean")
    if review.get("license_status") not in LICENSE_STATES:
        raise ValueError("invalid review.license_status")
    if review.get("safety_status") not in SAFETY_STATES:
        raise ValueError("invalid review.safety_status")
    for field in ("dependencies", "permissions", "evidence"):
        string_list(review.get(field, []), f"review.{field}")
    return payload


def recommend_adoption(payload: dict) -> tuple[str, str]:
    review = payload["review"]
    candidate_fingerprint = payload.get("candidate_behavior_fingerprint")
    existing_fingerprint = payload.get("existing_behavior_fingerprint")
    if candidate_fingerprint and candidate_fingerprint == existing_fingerprint:
        return (
            "reject",
            "candidate behavior fingerprint exactly matches the installed capability",
        )
    if review["license_status"] == "incompatible" or review["safety_status"] == "fail":
        return "reject", "license or safety review failed"
    if not review.get("unique_gain"):
        return "reject", "no measurable unique capability"
    if review["overlap_score"] >= 0.65 or not review["independent_boundary"]:
        return (
            "reference_strengthen",
            "useful gain exists but capability substantially overlaps "
            "an installed skill",
        )
    return (
        "full_install",
        "candidate has a distinct boundary and measurable unique capability",
    )


def command_adopt(args: argparse.Namespace) -> int:
    source = validate_candidate_review(read_json(Path(args.review)))
    candidate = source["candidate"]
    review = source["review"]
    recommendation, rationale = recommend_adoption(source)
    choice = args.choice
    review_fingerprint = object_fingerprint(source)
    output_path = Path(args.output)
    if output_path.exists():
        existing = read_json(output_path)
        if existing.get("review_fingerprint") == review_fingerprint and (
            choice is None or existing.get("user_choice") == choice
        ):
            print(f"Candidate adoption reused: status={existing.get('status')}")
            return 2 if existing.get("status") == "blocked" else 0
    blockers: list[str] = []
    if choice in {"full_install", "reference_strengthen"}:
        if review["license_status"] != "compatible":
            blockers.append("license must be confirmed compatible")
        if review["safety_status"] != "pass":
            blockers.append("safety review must pass")
        if (
            choice == "reference_strengthen"
            and not str(source.get("target_existing_skill", "")).strip()
        ):
            blockers.append("reference strengthening requires target_existing_skill")
    if choice is None:
        status = "awaiting_user_choice"
    elif choice == "reject":
        status = "rejected"
    elif blockers:
        status = "blocked"
    else:
        status = "ready_for_staging"
    recommendation_label = {
        "full_install": "完整安装",
        "reference_strengthen": "参考补强现有功能",
        "reject": "不采用",
    }[recommendation]
    question = (
        None
        if choice
        else (
            f"这个候选建议{recommendation_label}。您要完整安装，还是参考后补强现有功能？"
        )
    )
    payload = {
        "schema_version": 1,
        "artifact": "candidate-adoption",
        "review_fingerprint": review_fingerprint,
        "created_at": now_iso(),
        "candidate": candidate,
        "target_existing_skill": source.get("target_existing_skill"),
        "overlap": {
            "score": review["overlap_score"],
            "findings": source.get("overlap_findings", []),
        },
        "fingerprints": {
            "candidate": source.get("candidate_behavior_fingerprint"),
            "existing": source.get("existing_behavior_fingerprint"),
        },
        "unique_gain": review["unique_gain"],
        "recommendation": recommendation,
        "recommendation_rationale": rationale,
        "user_choice": choice,
        "status": status,
        "question": question,
        "license_status": review["license_status"],
        "safety_status": review["safety_status"],
        "dependencies": review["dependencies"],
        "permissions": review["permissions"],
        "evidence": review["evidence"],
        "blockers": blockers,
        "options": {
            "full_install": {
                "impact": (
                    "create a separately maintained Skill, preserve overlap mapping, "
                    "and start in probation"
                ),
                "write_scope": [candidate["identifier"]],
            },
            "reference_strengthen": {
                "impact": (
                    "patch only the existing Skill with licensed unique material and "
                    "create no duplicate directory"
                ),
                "write_scope": [source.get("target_existing_skill")],
            },
            "reject": {
                "impact": (
                    "record the decision and leave the active skill library unchanged"
                ),
                "write_scope": [],
            },
        },
        "write_scope": [source.get("target_existing_skill")]
        if choice == "reference_strengthen"
        else [candidate["identifier"]]
        if choice == "full_install"
        else [],
        "create_new_skill_directory": choice == "full_install",
        "initial_lifecycle": "probation"
        if choice == "full_install" and not blockers
        else None,
        "routing_priority": "low-overlap-trial"
        if choice == "full_install" and review["overlap_score"] >= 0.65
        else "normal-trial"
        if choice == "full_install"
        else None,
        "required_mapping_action": "record-overlap-and-lower-priority"
        if choice == "full_install" and review["overlap_score"] >= 0.65
        else "add-probation-route"
        if choice == "full_install"
        else "refresh-existing-fingerprint"
        if choice == "reference_strengthen"
        else None,
        "attribution_required": choice == "reference_strengthen",
        "rollback": (
            "restore the verified pre-change backup; no active skill is overwritten "
            "from discovery output"
        ),
    }
    write_json(output_path, payload)
    print(
        f"Candidate adoption: recommendation={recommendation}; "
        f"choice={choice or 'pending'}; status={status}"
    )
    return 2 if status == "blocked" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    assess = commands.add_parser(
        "assess", help="evaluate installed routes for a capability request"
    )
    assess.add_argument("--request", required=True)
    assess.add_argument(
        "--roadmap",
        default=str(
            Path(__file__).resolve().parents[1] / "registry" / "skill-roadmap.json"
        ),
    )
    assess.add_argument(
        "--registry",
        default=str(
            Path(__file__).resolve().parents[1] / "registry" / "skill-registry.json"
        ),
    )
    assess.add_argument("--output", required=True)
    assess.set_defaults(func=command_assess)
    resolve = commands.add_parser(
        "resolve", help="skip, search, or prepare creation after assessment"
    )
    resolve.add_argument("--request", required=True)
    resolve.add_argument("--decision", required=True)
    resolve.add_argument("--output", required=True)
    resolve.add_argument(
        "--online", choices=["never", "if-gap", "always"], default="if-gap"
    )
    resolve.add_argument("--gap-action", choices=["create", "improve", "use-tool"])
    resolve.add_argument("--limit", type=int, choices=range(1, 6), default=5)
    resolve.set_defaults(func=command_resolve)
    adopt = commands.add_parser(
        "adopt",
        help="recommend and record full install, reference strengthening, or rejection",
    )
    adopt.add_argument("--review", required=True)
    adopt.add_argument("--choice", choices=sorted(ADOPTION_MODES))
    adopt.add_argument("--output", required=True)
    adopt.set_defaults(func=command_adopt)
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
