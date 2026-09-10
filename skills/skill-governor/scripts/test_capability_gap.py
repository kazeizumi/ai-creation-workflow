#!/usr/bin/env python3
"""Forward tests for fit, search escalation, deduplication and adoption gates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("capability_gap.py")


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run(*args: str, expect: int = 0) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def request(
    request_id: str, lane: str = "writing", provided: dict | None = None
) -> dict:
    payload = {
        "schema_version": 1,
        "request_id": request_id,
        "deliverable": "validated article",
        "lane": lane,
        "stage": "draft",
        "input_types": ["brief"],
        "target_tools": ["markdown"],
        "constraints": ["concise"],
        "acceptance": ["article passes review"],
        "permissions": ["workspace-write"],
        "search_terms": ["agent writing skill"],
        "reusability": "repeatable",
        "non_obvious_risk": True,
    }
    if provided:
        payload["provided_candidate"] = provided
    return payload


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="capability-gap-") as raw:
        root = Path(raw)
        roadmap = root / "roadmap.json"
        registry = root / "registry.json"
        route = {
            "lane": "writing",
            "stage": "draft",
            "brief": "Drafts articles.",
            "use_when": "An article is required.",
            "boundary": "Does not publish.",
            "role": "primary",
            "review_level": "full-reviewed",
            "overlap_group": [],
            "input_types": ["brief"],
            "target_tools": ["markdown"],
        }
        write(roadmap, {"schema_version": 2, "skills": {"writer": route}})
        write(
            registry,
            {"schema_version": 2, "skills": {"writer": {"mapping_status": "current"}}},
        )

        fit_request = root / "fit-request.json"
        fit_decision = root / "fit-decision.json"
        fit_resolution = root / "fit-resolution.json"
        write(fit_request, request("fit-1"))
        run(
            "assess",
            "--request",
            str(fit_request),
            "--roadmap",
            str(roadmap),
            "--registry",
            str(registry),
            "--output",
            str(fit_decision),
        )
        fit = json.loads(fit_decision.read_text(encoding="utf-8"))
        assert (
            fit["result"] == "fit"
            and fit["selected_primary"] == "writer"
            and not fit["online_search_required"]
        )
        decision_before = fit_decision.read_bytes()
        assert (
            "reused"
            in run(
                "assess",
                "--request",
                str(fit_request),
                "--roadmap",
                str(roadmap),
                "--registry",
                str(registry),
                "--output",
                str(fit_decision),
            ).lower()
        )
        assert fit_decision.read_bytes() == decision_before
        run(
            "resolve",
            "--request",
            str(fit_request),
            "--decision",
            str(fit_decision),
            "--output",
            str(fit_resolution),
        )
        resolved = json.loads(fit_resolution.read_text(encoding="utf-8"))
        assert (
            resolved["status"] == "not_needed"
            and resolved["online_search"]["status"] == "skipped"
        )
        resolution_before = fit_resolution.read_bytes()
        assert (
            "reused"
            in run(
                "resolve",
                "--request",
                str(fit_request),
                "--decision",
                str(fit_decision),
                "--output",
                str(fit_resolution),
            ).lower()
        )
        assert fit_resolution.read_bytes() == resolution_before

        empty_registry = root / "empty-registry.json"
        empty_decision = root / "empty-decision.json"
        empty_resolution = root / "empty-resolution.json"
        write(empty_registry, {"schema_version": 2, "skills": {}})
        run(
            "assess",
            "--request",
            str(fit_request),
            "--roadmap",
            str(roadmap),
            "--registry",
            str(empty_registry),
            "--output",
            str(empty_decision),
        )
        run(
            "resolve",
            "--request",
            str(fit_request),
            "--decision",
            str(empty_decision),
            "--output",
            str(empty_resolution),
        )
        empty = json.loads(empty_resolution.read_text(encoding="utf-8"))
        assert (
            empty["status"] == "local_scan_required"
            and empty["online_search"]["status"] == "skipped"
        )

        gap_request = root / "gap-request.json"
        gap_decision = root / "gap-decision.json"
        gap_resolution = root / "gap-resolution.json"
        write(gap_request, request("gap-1", lane="audio"))
        run(
            "assess",
            "--request",
            str(gap_request),
            "--roadmap",
            str(roadmap),
            "--registry",
            str(registry),
            "--output",
            str(gap_decision),
        )
        run(
            "resolve",
            "--request",
            str(gap_request),
            "--decision",
            str(gap_decision),
            "--output",
            str(gap_resolution),
            "--online",
            "never",
        )
        gap = json.loads(gap_resolution.read_text(encoding="utf-8"))
        assert gap["status"] == "resolution_ready" and gap["gap_action"] == "create"
        assert gap["gap_spec"]["acceptance"] == ["article passes review"]

        provided_request = root / "provided-request.json"
        provided_decision = root / "provided-decision.json"
        provided_resolution = root / "provided-resolution.json"
        write(
            provided_request,
            request(
                "provided-1",
                provided={
                    "identifier": "https://example.test/skill",
                    "source": "user-provided",
                },
            ),
        )
        run(
            "assess",
            "--request",
            str(provided_request),
            "--roadmap",
            str(roadmap),
            "--registry",
            str(registry),
            "--output",
            str(provided_decision),
        )
        run(
            "resolve",
            "--request",
            str(provided_request),
            "--decision",
            str(provided_decision),
            "--output",
            str(provided_resolution),
        )
        provided = json.loads(provided_resolution.read_text(encoding="utf-8"))
        assert (
            provided["status"] == "candidate_review"
            and provided["online_search"]["status"] == "skipped"
        )

        review_path = root / "review.json"
        adoption_path = root / "adoption.json"
        base_review = {
            "candidate": {
                "identifier": "third-party-writer",
                "source": "user-provided",
                "url": "https://example.test/skill",
            },
            "target_existing_skill": "writer",
            "overlap_findings": ["same trigger and output"],
            "review": {
                "overlap_score": 0.8,
                "unique_gain": ["stronger rubric"],
                "independent_boundary": False,
                "license_status": "compatible",
                "safety_status": "pass",
                "dependencies": [],
                "permissions": [],
                "evidence": ["same-request comparison"],
            },
        }
        write(review_path, base_review)
        run("adopt", "--review", str(review_path), "--output", str(adoption_path))
        adoption = json.loads(adoption_path.read_text(encoding="utf-8"))
        assert adoption["recommendation"] == "reference_strengthen"
        assert adoption["status"] == "awaiting_user_choice" and adoption["question"]
        run(
            "adopt",
            "--review",
            str(review_path),
            "--choice",
            "reference_strengthen",
            "--output",
            str(adoption_path),
        )
        adoption = json.loads(adoption_path.read_text(encoding="utf-8"))
        assert (
            adoption["status"] == "ready_for_staging"
            and not adoption["create_new_skill_directory"]
            and adoption["question"] is None
        )
        assert adoption["attribution_required"] and adoption["options"][
            "reference_strengthen"
        ]["write_scope"] == ["writer"]
        adoption_before = adoption_path.read_bytes()
        assert (
            "reused"
            in run(
                "adopt", "--review", str(review_path), "--output", str(adoption_path)
            ).lower()
        )
        assert adoption_path.read_bytes() == adoption_before
        run(
            "adopt",
            "--review",
            str(review_path),
            "--choice",
            "full_install",
            "--output",
            str(adoption_path),
        )
        assert (
            json.loads(adoption_path.read_text(encoding="utf-8"))["routing_priority"]
            == "low-overlap-trial"
        )

        distinct = json.loads(json.dumps(base_review))
        distinct["review"].update({"overlap_score": 0.2, "independent_boundary": True})
        write(review_path, distinct)
        run(
            "adopt",
            "--review",
            str(review_path),
            "--choice",
            "full_install",
            "--output",
            str(adoption_path),
        )
        adoption = json.loads(adoption_path.read_text(encoding="utf-8"))
        assert (
            adoption["recommendation"] == "full_install"
            and adoption["initial_lifecycle"] == "probation"
        )

        duplicate = json.loads(json.dumps(base_review))
        duplicate["candidate_behavior_fingerprint"] = "same-hash"
        duplicate["existing_behavior_fingerprint"] = "same-hash"
        write(review_path, duplicate)
        run("adopt", "--review", str(review_path), "--output", str(adoption_path))
        assert (
            json.loads(adoption_path.read_text(encoding="utf-8"))["recommendation"]
            == "reject"
        )

        unsafe = json.loads(json.dumps(distinct))
        unsafe["review"]["safety_status"] = "unknown"
        write(review_path, unsafe)
        run(
            "adopt",
            "--review",
            str(review_path),
            "--choice",
            "full_install",
            "--output",
            str(adoption_path),
            expect=2,
        )
        assert (
            json.loads(adoption_path.read_text(encoding="utf-8"))["status"] == "blocked"
        )
    print("capability gap tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
