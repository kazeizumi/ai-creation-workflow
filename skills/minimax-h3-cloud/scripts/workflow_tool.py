#!/usr/bin/env python3
"""Inspect and run an exact workflow already installed on an AutoDL H3 panel."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

try:
    import httpx
except ImportError as exc:  # pragma: no cover - dependency diagnostic
    raise SystemExit("Missing dependency: install httpx in the active Python environment") from exc

PANEL_SUFFIXES = (".autodl.com", ".autodl.art", ".seetacloud.com")
MEDIA_CLASSES = {
    "image": ("loadimage",),
    "video": ("loadvideo",),
    "audio": ("loadaudio",),
}


class WorkflowError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def safe_base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    clean_origin = (
        parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )
    allowed_remote = parsed.scheme == "https" and any(
        host.endswith(suffix) for suffix in PANEL_SUFFIXES
    ) and clean_origin
    allowed_local = (
        os.environ.get("H3_CLOUD_ALLOW_LOCALHOST") == "1"
        and parsed.scheme in {"http", "https"}
        and host in {"127.0.0.1", "localhost", "::1"}
        and clean_origin
    )
    if not (allowed_remote or allowed_local):
        raise WorkflowError(
            "Panel URL must be a clean HTTPS origin on an AutoDL/SeetaCloud domain. "
            "Local test servers require H3_CLOUD_ALLOW_LOCALHOST=1."
        )
    return url


def make_client(timeout: int = 180) -> httpx.Client:
    return httpx.Client(timeout=timeout, verify=True, follow_redirects=False)


def response_json(response: httpx.Response, operation: str) -> dict:
    response.raise_for_status()
    try:
        value = response.json()
    except ValueError as exc:
        raise WorkflowError(f"{operation} returned non-JSON data") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{operation} returned an unexpected JSON type")
    return value


def list_workflows(client: httpx.Client, base_url: str) -> list[dict]:
    data = response_json(client.get(base_url + "/api/workflow/list"), "workflow list")
    workflows = data.get("workflows") or []
    if not isinstance(workflows, list):
        raise WorkflowError("workflow list has no workflows array")
    return [item for item in workflows if isinstance(item, dict)]


def workflow_id(item: dict) -> str:
    return str(item.get("id") or item.get("workflow_id") or item.get("name") or "")


def assert_workflow_exists(client: httpx.Client, base_url: str, selected: str) -> dict:
    matches = [item for item in list_workflows(client, base_url) if workflow_id(item) == selected]
    if len(matches) != 1:
        available = [workflow_id(item) for item in list_workflows(client, base_url)]
        raise WorkflowError(
            f"Installed workflow {selected!r} was not found exactly. Available IDs: {available}"
        )
    return matches[0]


def fetch_workflow(client: httpx.Client, base_url: str, selected: str) -> dict:
    assert_workflow_exists(client, base_url, selected)
    encoded = quote(selected, safe="")
    return response_json(
        client.get(f"{base_url}/workflows/{encoded}.json"), "workflow definition"
    )


def iter_nodes(workflow: dict):
    nodes = workflow.get("nodes", workflow)
    if isinstance(nodes, dict):
        for node_id, node in nodes.items():
            if isinstance(node, dict):
                yield str(node_id), node
    elif isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                yield str(node.get("id")), node


def class_name(node: dict) -> str:
    return str(node.get("class_type") or node.get("type") or "")


def is_link(value: object) -> bool:
    return isinstance(value, list) and len(value) >= 2


def inspect_workflow(client: httpx.Client, base_url: str, selected: str) -> dict:
    workflow = fetch_workflow(client, base_url, selected)
    scalar_inputs: list[dict] = []
    media_inputs: dict[str, list[dict]] = {key: [] for key in MEDIA_CLASSES}
    suggested: dict[str, list[str]] = {
        "prompt": [],
        "duration": [],
        "width": [],
        "height": [],
        "steps": [],
        "lora": [],
    }
    for node_id, node in iter_nodes(workflow):
        cls = class_name(node)
        low_cls = cls.casefold()
        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue
        for input_name, current in inputs.items():
            key = f"{node_id}:{input_name}"
            if not is_link(current):
                scalar_inputs.append(
                    {
                        "key": key,
                        "node_class": cls,
                        "input_name": input_name,
                        "current": current,
                    }
                )
                low_name = str(input_name).casefold()
                if low_name in {"prompt", "text", "positive", "提示词", "正文"}:
                    suggested["prompt"].append(key)
                if low_name in {"seconds", "duration", "value", "秒数", "时长", "视频时长"}:
                    if isinstance(current, (int, float)) and 3 <= float(current) <= 60:
                        suggested["duration"].append(key)
                if low_name in {"width", "自定义宽"}:
                    suggested["width"].append(key)
                if low_name in {"height", "自定义高"}:
                    suggested["height"].append(key)
                if low_name == "steps":
                    suggested["steps"].append(key)
                if low_name == "lora_name":
                    suggested["lora"].append(key)
        for media_type, hints in MEDIA_CLASSES.items():
            if any(hint in low_cls for hint in hints):
                candidate_name = media_type
                if candidate_name in inputs:
                    media_inputs[media_type].append(
                        {
                            "key": f"{node_id}:{candidate_name}",
                            "node_class": cls,
                            "current": inputs.get(candidate_name),
                        }
                    )
    return {
        "workflow_id": selected,
        "media_inputs": media_inputs,
        "suggested_bindings": suggested,
        "scalar_inputs": scalar_inputs,
        "warning": "Suggested bindings are heuristic; review them before a paid run.",
    }


def resolve_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def upload_file(client: httpx.Client, base_url: str, path: Path) -> str:
    if not path.is_file():
        raise WorkflowError(f"Upload file does not exist: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        response = client.post(
            base_url + "/api/comfy/upload/file",
            files={"file": (path.name, handle, mime)},
            data={"overwrite": "true"},
        )
    data = response_json(response, f"upload {path.name}")
    remote_name = data.get("name")
    if not isinstance(remote_name, str) or not remote_name:
        raise WorkflowError(f"Upload response for {path.name} has no remote name")
    log(f"uploaded {path.name} -> {remote_name}")
    return remote_name


def resolve_upload_markers(
    client: httpx.Client, base_url: str, value: object, base_dir: Path
) -> object:
    if isinstance(value, dict):
        if "$upload" in value:
            if set(value) != {"$upload"} or not isinstance(value["$upload"], str):
                raise WorkflowError("An $upload marker must contain only one string path")
            return upload_file(client, base_url, resolve_path(value["$upload"], base_dir))
        return {
            key: resolve_upload_markers(client, base_url, item, base_dir)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [resolve_upload_markers(client, base_url, item, base_dir) for item in value]
    return value


def submit_job(
    client: httpx.Client, base_url: str, job: dict, base_dir: Path
) -> dict:
    selected = str(job.get("workflow_id") or "")
    if not selected:
        raise WorkflowError("Each job requires an exact workflow_id")
    assert_workflow_exists(client, base_url, selected)
    raw_inputs = job.get("input_values")
    if not isinstance(raw_inputs, dict) or not raw_inputs:
        raise WorkflowError(f"Job {job.get('name')!r} requires non-empty input_values")
    inputs = resolve_upload_markers(client, base_url, raw_inputs, base_dir)
    response = client.post(
        base_url + "/api/workflow/generate",
        json={"workflow_id": selected, "input_values": inputs},
    )
    data = response_json(response, f"submit {job.get('name') or selected}")
    if not data.get("success"):
        raise WorkflowError(f"Workflow submission failed: {data}")
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise WorkflowError(f"Submission response has no prompt_id: {data}")
    return {
        "name": job.get("name") or str(prompt_id),
        "workflow_id": selected,
        "prompt_id": str(prompt_id),
        "output": job.get("output"),
        "status": "submitted",
    }


def history_entry(client: httpx.Client, base_url: str, prompt_id: str) -> dict | None:
    response = client.get(
        base_url + "/api/comfy/proxy/history", params={"prompt_id": prompt_id}
    )
    data = response_json(response, "prompt history")
    entry = data.get(prompt_id)
    return entry if isinstance(entry, dict) else None


def queue_ids(client: httpx.Client, base_url: str) -> set[str]:
    try:
        data = response_json(
            client.get(base_url + "/api/comfy/queue-status"), "queue status"
        )
    except Exception:
        return set()
    values: set[str] = set()
    for key in ("queue_running", "queue_pending"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("prompt_id"):
                values.add(str(item["prompt_id"]))
    for item in data.get("prompt_ids") or []:
        values.add(str(item))
    return values


def mp4_paths(entry: dict) -> list[str]:
    found: list[str] = []
    for output in (entry.get("outputs") or {}).values():
        if not isinstance(output, dict):
            continue
        for collection in ("videos", "images", "gifs", "files"):
            for item in output.get(collection) or []:
                candidate = ""
                subfolder = ""
                if isinstance(item, str):
                    candidate = item
                elif isinstance(item, dict):
                    candidate = str(item.get("url") or item.get("filename") or item.get("name") or "")
                    subfolder = str(item.get("subfolder") or "").strip("/")
                clean = candidate.split("?", 1)[0]
                if not clean.casefold().endswith(".mp4"):
                    continue
                if clean.startswith(("http://", "https://", "/")):
                    result = clean
                elif subfolder:
                    result = f"/output/{subfolder}/{Path(clean).name}"
                else:
                    result = f"/output/{Path(clean).name}"
                if result not in found:
                    found.append(result)
    return found


def execution_error(entry: dict) -> object | None:
    for message in (entry.get("status") or {}).get("messages") or []:
        if isinstance(message, (list, tuple)) and len(message) >= 2 and message[0] == "execution_error":
            return message[1]
    return None


def safe_download_url(base_url: str, remote: str) -> str:
    url = remote if remote.startswith(("http://", "https://")) else urljoin(base_url + "/", remote.lstrip("/"))
    parsed = urlparse(url)
    base_parsed = urlparse(safe_base_url(base_url))
    base_host = (base_parsed.hostname or "").casefold()
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != base_parsed.scheme or host != base_host:
        raise WorkflowError("Refusing a result URL outside the selected panel origin")
    return url


def stream_download(
    client: httpx.Client,
    base_url: str,
    remote: str,
    destination: Path,
    overwrite: bool,
) -> dict:
    if destination.exists() and not overwrite:
        raise WorkflowError(f"Output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    if part.exists():
        part.unlink()
    url = safe_download_url(base_url, remote)
    written = 0
    try:
        with client.stream("GET", url, timeout=600) as response:
            response.raise_for_status()
            with part.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
                    written += len(chunk)
        if written == 0:
            raise WorkflowError("Downloaded result is empty")
        os.replace(part, destination)
    except Exception:
        if part.exists():
            part.unlink()
        raise
    return {"path": str(destination), "bytes": written, "source": url}


def probe_video(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        bundled_ffprobe = Path("C:/tools/ffmpeg/ffprobe.exe")
        if bundled_ffprobe.is_file():
            ffprobe = str(bundled_ffprobe)
    if not ffprobe:
        return {"available": False, "warning": "ffprobe was not found"}
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise WorkflowError(f"ffprobe failed for {path}: {completed.stderr[-1000:]}")
    return {"available": True, "result": json.loads(completed.stdout)}


def poll_task(
    base_url: str,
    task: dict,
    destination: Path,
    *,
    timeout: int,
    overwrite: bool,
) -> dict:
    prompt_id = str(task["prompt_id"])
    deadline = time.monotonic() + timeout
    with make_client(60) as client:
        while time.monotonic() < deadline:
            entry = history_entry(client, base_url, prompt_id)
            if entry:
                error = execution_error(entry)
                if error is not None:
                    raise WorkflowError(
                        f"Remote execution failed for {prompt_id}: "
                        + json.dumps(error, ensure_ascii=False)
                    )
                outputs = mp4_paths(entry)
                if outputs:
                    download = stream_download(
                        client, base_url, outputs[0], destination, overwrite
                    )
                    return {
                        **task,
                        "status": "succeeded",
                        "download": download,
                        "ffprobe": probe_video(destination),
                    }
            queued = prompt_id in queue_ids(client, base_url)
            log(f"prompt {prompt_id}: {'queued/running' if queued else 'waiting for history'}")
            time.sleep(15)
    raise WorkflowError(f"Timed out waiting for prompt {prompt_id}")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"JSON file must contain an object: {path}")
    return value


def command_list(args: argparse.Namespace) -> None:
    base_url = safe_base_url(args.base_url)
    with make_client(60) as client:
        items = list_workflows(client, base_url)
    emit(
        {
            "panel_url": base_url,
            "workflows": [
                {
                    "workflow_id": workflow_id(item),
                    "run_count": item.get("run_count"),
                    "title": item.get("title") or item.get("name"),
                }
                for item in items
            ],
        }
    )


def command_inspect(args: argparse.Namespace) -> None:
    base_url = safe_base_url(args.base_url)
    with make_client(60) as client:
        report = inspect_workflow(client, base_url, args.workflow_id)
    if args.out:
        path = Path(args.out).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit(report)


def command_submit(args: argparse.Namespace) -> None:
    base_url = safe_base_url(args.base_url)
    job_path = Path(args.job).resolve()
    job = load_json(job_path)
    with make_client(300) as client:
        task = submit_job(client, base_url, job, job_path.parent)
    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    emit(task)


def command_poll(args: argparse.Namespace) -> None:
    base_url = safe_base_url(args.base_url)
    task_path = Path(args.task).resolve()
    task = load_json(task_path)
    destination = resolve_path(args.download, task_path.parent)
    emit(
        poll_task(
            base_url,
            task,
            destination,
            timeout=args.timeout,
            overwrite=args.overwrite,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "inspect", "submit", "poll"):
        item = subparsers.add_parser(name)
        item.add_argument("--base-url", required=True)
        if name == "list":
            item.set_defaults(func=command_list)
        elif name == "inspect":
            item.add_argument("--workflow-id", required=True)
            item.add_argument("--out")
            item.set_defaults(func=command_inspect)
        elif name == "submit":
            item.add_argument("--job", required=True)
            item.add_argument("--out")
            item.set_defaults(func=command_submit)
        else:
            item.add_argument("--task", required=True)
            item.add_argument("--download", required=True)
            item.add_argument("--timeout", type=int, default=3600)
            item.add_argument("--overwrite", action="store_true")
            item.set_defaults(func=command_poll)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.func(args)
        return 0
    except (WorkflowError, httpx.HTTPError, OSError, ValueError) as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
