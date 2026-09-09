#!/usr/bin/env python3
"""Run a manifest as one owned AutoDL H3 batch with finally-based shutdown."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import workflow_tool


class BatchError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError(f"Cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BatchError("Batch manifest must contain a JSON object")
    return value


def resolve_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def locate_instance_tool(explicit: str) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    package_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            package_root / "autodl-app-instance" / "scripts" / "autodl_instance.py",
            Path.home() / ".codex" / "skills" / "autodl-app-instance" / "scripts" / "autodl_instance.py",
            Path.home() / ".agents" / "skills" / "autodl-app-instance" / "scripts" / "autodl_instance.py",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise BatchError("Cannot find autodl_instance.py; pass --instance-tool explicitly")


def run_instance_tool(tool: Path, *arguments: str) -> dict:
    command = [sys.executable, str(tool), *arguments]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode != 0:
        raise BatchError(
            f"Instance command failed ({completed.returncode}): {completed.stdout[-1000:]}"
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise BatchError("Instance tool returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise BatchError("Instance tool returned an unexpected JSON type")
    return value


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def validate_manifest(manifest: dict, manifest_path: Path, args: argparse.Namespace) -> dict:
    uuid = str(manifest.get("instance_uuid") or "").strip()
    if not re_uuid(uuid):
        raise BatchError("instance_uuid must be an exact AutoDL application ID such as pro-xxxxxxxxxxxx")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise BatchError("Manifest requires a non-empty jobs array")
    base_dir = manifest_path.parent
    normalized_jobs: list[dict] = []
    names: set[str] = set()
    outputs: set[str] = set()
    overwrite = bool(manifest.get("overwrite_outputs", False))
    for index, raw in enumerate(jobs, 1):
        if not isinstance(raw, dict):
            raise BatchError(f"Job {index} must be an object")
        name = str(raw.get("name") or f"job-{index:03d}")
        selected = str(raw.get("workflow_id") or "").strip()
        output_raw = str(raw.get("output") or "").strip()
        inputs = raw.get("input_values")
        if name in names:
            raise BatchError(f"Duplicate job name: {name}")
        if not selected:
            raise BatchError(f"Job {name} has no workflow_id")
        if not isinstance(inputs, dict) or not inputs:
            raise BatchError(f"Job {name} requires non-empty input_values")
        if not output_raw:
            raise BatchError(f"Job {name} has no output path")
        output = resolve_path(output_raw, base_dir)
        output_key = os.path.normcase(str(output))
        if output_key in outputs:
            raise BatchError(f"Duplicate output path: {output}")
        if output.exists() and not overwrite:
            raise BatchError(f"Output already exists and overwrite_outputs is false: {output}")
        names.add(name)
        outputs.add(output_key)
        normalized_jobs.append({**raw, "name": name, "workflow_id": selected, "output": str(output)})
    keep_on = bool(manifest.get("keep_on", False))
    if keep_on and not args.allow_keep_on:
        raise BatchError(
            "Manifest requests keep_on=true; repeat with --allow-keep-on only after the user explicitly asks"
        )
    state_raw = str(manifest.get("state_file") or "batch-state.json")
    return {
        "instance_uuid": uuid,
        "jobs": normalized_jobs,
        "keep_on": keep_on,
        "overwrite_outputs": overwrite,
        "poll_timeout_seconds": int(manifest.get("poll_timeout_seconds") or 3600),
        "max_parallel_polls": max(1, min(int(manifest.get("max_parallel_polls") or 3), 8)),
        "state_file": str(resolve_path(state_raw, base_dir)),
        "base_dir": str(base_dir),
    }


def re_uuid(value: str) -> bool:
    if not value.startswith("pro-"):
        return False
    suffix = value[4:]
    return 8 <= len(suffix) <= 64 and all(char.isalnum() or char in "-_" for char in suffix)


def state_skeleton(config: dict) -> dict:
    return {
        "instance_uuid": config["instance_uuid"],
        "phase": "validated",
        "panel_url": None,
        "jobs": [
            {
                "name": job["name"],
                "workflow_id": job["workflow_id"],
                "output": job["output"],
                "status": "pending",
            }
            for job in config["jobs"]
        ],
        "shutdown": "not_started",
    }


def update_job_state(state: dict, name: str, **values: object) -> None:
    for item in state["jobs"]:
        if item["name"] == name:
            item.update(values)
            return
    raise BatchError(f"Unknown state job {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--instance-tool", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--adopt-running-instance", action="store_true")
    parser.add_argument("--allow-keep-on", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    instance_tool = locate_instance_tool(args.instance_tool)
    config = validate_manifest(load_manifest(manifest_path), manifest_path, args)
    state_path = Path(config["state_file"])
    state = state_skeleton(config)
    atomic_json(state_path, state)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "valid": True,
                    "instance_tool": str(instance_tool),
                    "instance_uuid": config["instance_uuid"],
                    "job_count": len(config["jobs"]),
                    "state_file": str(state_path),
                    "outputs": [job["output"] for job in config["jobs"]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    booted = False
    return_code = 1
    try:
        current = run_instance_tool(
            instance_tool, "status", "--uuid", config["instance_uuid"]
        )
        if current.get("status") == "running" and not args.adopt_running_instance:
            raise BatchError(
                "Instance is already running. Inspect its queue, then pass "
                "--adopt-running-instance if this batch may own its shutdown."
            )
        boot = run_instance_tool(
            instance_tool, "boot", "--uuid", config["instance_uuid"]
        )
        booted = True
        base_url = workflow_tool.safe_base_url(str(boot["panel_url"]))
        state["phase"] = "submitting"
        state["panel_url"] = base_url
        atomic_json(state_path, state)

        tasks: list[dict] = []
        with workflow_tool.make_client(300) as client:
            for job in config["jobs"]:
                task = workflow_tool.submit_job(
                    client, base_url, job, Path(config["base_dir"])
                )
                tasks.append(task)
                update_job_state(
                    state,
                    job["name"],
                    status="submitted",
                    prompt_id=task["prompt_id"],
                )
                atomic_json(state_path, state)

        state["phase"] = "polling"
        atomic_json(state_path, state)
        executor = ThreadPoolExecutor(max_workers=config["max_parallel_polls"])
        future_to_task = {
            executor.submit(
                workflow_tool.poll_task,
                base_url,
                task,
                Path(task["output"]),
                timeout=config["poll_timeout_seconds"],
                overwrite=config["overwrite_outputs"],
            ): task
            for task in tasks
        }
        try:
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                result = future.result()
                update_job_state(
                    state,
                    task["name"],
                    status="succeeded",
                    ffprobe=result.get("ffprobe"),
                    bytes=(result.get("download") or {}).get("bytes"),
                )
                atomic_json(state_path, state)
        except Exception:
            for future in future_to_task:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

        state["phase"] = "complete"
        atomic_json(state_path, state)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return_code = 0
    except Exception as exc:
        state["phase"] = "failed"
        state["error"] = str(exc)
        atomic_json(state_path, state)
        log(f"ERROR: {exc}")
        return_code = 1
    finally:
        if booted and not config["keep_on"]:
            try:
                run_instance_tool(
                    instance_tool,
                    "off",
                    "--uuid",
                    config["instance_uuid"],
                    "--wait",
                )
                state["shutdown"] = "complete"
            except Exception as cleanup_error:
                state["shutdown"] = "failed"
                state["shutdown_error"] = str(cleanup_error)
                log(f"CRITICAL: automatic shutdown failed: {cleanup_error}")
                return_code = 2
            atomic_json(state_path, state)
        elif booted:
            state["shutdown"] = "skipped_keep_on"
            atomic_json(state_path, state)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
