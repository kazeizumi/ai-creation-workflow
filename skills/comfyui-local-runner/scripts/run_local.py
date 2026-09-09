#!/usr/bin/env python3
"""Manifest-driven local ComfyUI API workflow runner."""

from __future__ import annotations

import argparse
import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def request_json(url: str, *, payload: dict | None = None, timeout: float = 30) -> dict:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def multipart_file(field: str, path: Path) -> tuple[bytes, str]:
    boundary = "----ai-creation-" + uuid.uuid4().hex
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {media_type}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), boundary


def upload(base_url: str, path: Path) -> str:
    body, boundary = multipart_file("image", path)
    request = urllib.request.Request(
        base_url.rstrip("/") + "/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    name = result.get("name")
    if not name:
        raise RuntimeError(f"Upload response has no filename for {path.name}")
    subfolder = result.get("subfolder") or ""
    return f"{subfolder}/{name}".lstrip("/") if subfolder else str(name)


def validate(manifest_path: Path) -> tuple[dict, dict, list[tuple[str, str, object]]]:
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    folder = manifest_path.parent
    workflow_path = resolve(folder, str(manifest.get("workflow", "")))
    if not workflow_path.is_file():
        raise FileNotFoundError(f"Workflow not found: {workflow_path}")
    workflow = read_json(workflow_path)
    if not workflow or any(not isinstance(node, dict) or not isinstance(node.get("inputs"), dict) for node in workflow.values()):
        raise ValueError("Workflow is not ComfyUI API format")
    patches: list[tuple[str, str, object]] = []
    for key, value in manifest.get("input_values", {}).items():
        if ":" not in key:
            raise ValueError(f"Input key must be node_id:input_name: {key}")
        node_id, field = key.split(":", 1)
        if node_id not in workflow or field not in workflow[node_id]["inputs"]:
            raise ValueError(f"Workflow input not found: {key}")
        if isinstance(value, dict) and "$upload" in value:
            path = resolve(folder, str(value["$upload"]))
            if not path.is_file():
                raise FileNotFoundError(f"Upload input not found: {path}")
        elif isinstance(value, dict) and "$text_file" in value:
            path = resolve(folder, str(value["$text_file"]))
            if not path.is_file():
                raise FileNotFoundError(f"Text input not found: {path}")
        elif isinstance(value, dict) and any(str(item).startswith("$") for item in value):
            raise ValueError(f"Unsupported manifest directive at {key}")
        patches.append((node_id, field, value))
    return manifest, workflow, patches


def output_items(history: dict) -> list[dict]:
    items: list[dict] = []
    for node in history.get("outputs", {}).values():
        for collection in ("images", "gifs", "videos", "audio"):
            for item in node.get(collection, []) if isinstance(node, dict) else []:
                if isinstance(item, dict) and item.get("filename"):
                    items.append(item)
    unique: dict[tuple[str, str, str], dict] = {}
    for item in items:
        key = (str(item.get("filename")), str(item.get("subfolder", "")), str(item.get("type", "output")))
        unique[key] = item
    return list(unique.values())


def download(base_url: str, item: dict, output_dir: Path) -> Path:
    query = urllib.parse.urlencode({
        "filename": item["filename"],
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
    })
    destination = output_dir / Path(str(item.get("subfolder", ""))) / Path(str(item["filename"])).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(base_url.rstrip("/") + "/view?" + query, timeout=300) as response, part.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    part.replace(destination)
    return destination


def run(manifest_path: Path, *, dry_run: bool, allow_remote: bool) -> int:
    manifest, workflow, patches = validate(manifest_path)
    base_url = str(manifest.get("base_url", "http://127.0.0.1:8188")).rstrip("/")
    host = urllib.parse.urlparse(base_url).hostname
    if not allow_remote and host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Non-loopback base_url requires --allow-remote")
    upload_count = sum(isinstance(value, dict) and "$upload" in value for _, _, value in patches)
    print(f"Validated workflow nodes={len(workflow)} patches={len(patches)} uploads={upload_count}")
    if dry_run:
        print("Dry run complete; no uploads or prompt submission performed.")
        return 0

    folder = manifest_path.parent
    for node_id, field, value in patches:
        if isinstance(value, dict) and "$upload" in value:
            final = upload(base_url, resolve(folder, str(value["$upload"])))
        elif isinstance(value, dict) and "$text_file" in value:
            final = resolve(folder, str(value["$text_file"])).read_text(encoding="utf-8")
        else:
            final = value
        workflow[node_id]["inputs"][field] = final

    client_id = uuid.uuid4().hex
    submitted = request_json(base_url + "/prompt", payload={"prompt": workflow, "client_id": client_id}, timeout=60)
    prompt_id = str(submitted.get("prompt_id") or "")
    if not prompt_id:
        raise RuntimeError(f"Prompt submission returned no prompt_id: {submitted}")
    output_dir = resolve(folder, str(manifest.get("output_dir", "results")))
    state_path = output_dir / "run-state.json"
    state = {"schema_version": 1, "status": "submitted", "prompt_id": prompt_id, "client_id": client_id, "outputs": []}
    write_json(state_path, state)
    deadline = time.monotonic() + float(manifest.get("timeout_seconds", 7200))
    interval = max(1.0, float(manifest.get("poll_seconds", 5)))
    history: dict | None = None
    while time.monotonic() < deadline:
        payload = request_json(base_url + "/history/" + urllib.parse.quote(prompt_id), timeout=30)
        if prompt_id in payload:
            history = payload[prompt_id]
            break
        time.sleep(interval)
    if history is None:
        state["status"] = "timeout"
        write_json(state_path, state)
        raise TimeoutError(f"Timed out; inspect existing prompt_id={prompt_id} before retrying")
    status = history.get("status", {})
    if isinstance(status, dict) and status.get("status_str") == "error":
        state["status"] = "failed"
        state["history_status"] = status
        write_json(state_path, state)
        raise RuntimeError(f"ComfyUI prompt failed: {prompt_id}")
    items = output_items(history)
    if not items:
        raise RuntimeError(f"Prompt completed without downloadable outputs: {prompt_id}")
    paths = [str(download(base_url, item, output_dir)) for item in items]
    state["status"] = "completed"
    state["outputs"] = paths
    write_json(state_path, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    try:
        return run(Path(args.manifest).resolve(), dry_run=args.dry_run, allow_remote=args.allow_remote)
    except (OSError, ValueError, RuntimeError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
