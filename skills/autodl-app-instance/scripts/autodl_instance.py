#!/usr/bin/env python3
"""Secure AutoDL Art application-instance lifecycle helper."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode, urlparse

API_HOST = "https://www.autodl.art"
API_PREFIX = "/api/v1/adl_dev/dev/instance/pro"
PANEL_SUFFIXES = (".autodl.com", ".autodl.art", ".seetacloud.com")
REDACT_KEYS = {"root_password", "jupyter_token", "token", "authorization"}


class ApiError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def env_file_path() -> Path:
    override = os.environ.get("AUTODL_ENV_FILE", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".config" / "autodl.env"


def read_assignment(path: Path, key: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*(.*?)\s*$")
    for line in lines:
        match = pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value.strip()
    return ""


def developer_token() -> str:
    value = os.environ.get("AUTODL_TOKEN", "").strip() or read_assignment(
        env_file_path(), "AUTODL_TOKEN"
    )
    if value.lower().startswith("bearer "):
        value = value.split(None, 1)[1].strip()
    if not value:
        raise ApiError(
            "Missing AUTODL_TOKEN. Set it in the process environment or in "
            f"{env_file_path()}."
        )
    return value


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(
        url, data=body, method=method, headers=request_headers
    )
    try:
        with urllib.request.urlopen(
            req, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise ApiError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ApiError(f"Request failed for {url}: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(f"Non-JSON response from {url}") from exc
    if not isinstance(value, dict):
        raise ApiError(f"Unexpected response type from {url}")
    return value


def api_call(method: str, path: str, payload: dict | None = None) -> object:
    url = API_HOST + API_PREFIX + path
    request_payload = payload
    if method.upper() == "GET" and payload:
        url += "?" + urlencode(payload)
        request_payload = None
    value = request_json(
        url,
        method=method,
        payload=request_payload,
        headers={"Authorization": developer_token()},
    )
    if value.get("code") != "Success":
        raise ApiError(
            f"AutoDL API error at {path}: code={value.get('code')!r}, "
            f"message={value.get('msg')!r}"
        )
    return value.get("data")


def list_instances() -> list[dict]:
    first = api_call("POST", "/list", {"page_index": 1, "page_size": 100})
    if not isinstance(first, dict):
        raise ApiError("AutoDL list response has no data object")
    items = list(first.get("list") or [])
    max_page = min(int(first.get("max_page") or 1), 100)
    for page in range(2, max_page + 1):
        data = api_call("POST", "/list", {"page_index": page, "page_size": 100})
        if isinstance(data, dict):
            items.extend(data.get("list") or [])
    return [item for item in items if isinstance(item, dict)]


def instance_status(uuid: str) -> str:
    return str(api_call("GET", "/status", {"instance_uuid": uuid}) or "")


def instance_snapshot(uuid: str) -> dict:
    data = api_call("GET", "/snapshot", {"instance_uuid": uuid})
    if not isinstance(data, dict):
        raise ApiError("AutoDL snapshot response has no data object")
    return data


def power_on(uuid: str) -> None:
    api_call("POST", "/power_on", {"instance_uuid": uuid, "payload": "gpu"})


def power_off(uuid: str) -> None:
    api_call("POST", "/power_off", {"instance_uuid": uuid})


def app_name(item: dict) -> str:
    return str((item.get("cg_application_info") or {}).get("application_name") or "")


def instance_summary(item: dict) -> dict:
    return {
        "uuid": item.get("uuid"),
        "status": item.get("status"),
        "region": item.get("region_name"),
        "name": item.get("name"),
        "application_name": app_name(item),
        "gpu_spec_uuid": item.get("gpu_spec_uuid"),
    }


def resolve_uuid(args: argparse.Namespace) -> str:
    explicit = (getattr(args, "uuid", "") or "").strip()
    env_value = os.environ.get("AUTODL_INSTANCE_UUID", "").strip()
    if explicit or env_value:
        return explicit or env_value
    hint = (getattr(args, "app_hint", "") or "MINIMAX-H3").casefold()
    matches = [
        item
        for item in list_instances()
        if hint in app_name(item).casefold() or hint in str(item.get("name") or "").casefold()
    ]
    if len(matches) == 1:
        return str(matches[0]["uuid"])
    if not matches:
        raise ApiError(f"No AutoDL application instance matched {hint!r}")
    candidates = json.dumps(
        [instance_summary(item) for item in matches], ensure_ascii=False
    )
    raise ApiError(f"Multiple instances matched; choose --uuid from: {candidates}")


def wait_for_status(uuid: str, targets: set[str], timeout: int) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = instance_status(uuid)
        log(f"instance {uuid}: {last}")
        if last in targets:
            return last
        time.sleep(5)
    raise ApiError(f"Timed out waiting for {sorted(targets)}; last status={last!r}")


def redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.casefold() in REDACT_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def allowed_panel_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(host.endswith(suffix) for suffix in PANEL_SUFFIXES)


def panel_candidates(snapshot: dict) -> list[str]:
    candidates: list[str] = []
    for key, raw_domain in snapshot.items():
        match = re.fullmatch(r"service_(\d+)_domain", str(key))
        if not match or not raw_domain:
            continue
        domain = str(raw_domain).strip().strip("/")
        stem = key[: -len("_domain")]
        protocol = str(snapshot.get(stem + "_port_protocol") or "").casefold()
        if re.search(r":(?:443|8443)$", domain):
            protocol = "https"
        if not protocol:
            protocol = "https"
        if "://" in domain:
            url = domain
        else:
            port = str(snapshot.get(stem + "_port") or "").strip()
            suffix = "" if ":" in domain or not port or port == "0" else f":{port}"
            url = f"{protocol}://{domain}{suffix}"
        if allowed_panel_url(url) and url not in candidates:
            candidates.append(url)
    return candidates


def panel_probe(base_url: str, timeout: int = 8) -> tuple[str, dict | None]:
    try:
        value = request_json(base_url.rstrip("/") + "/api/comfy/status", timeout=timeout)
    except ApiError:
        return "dead", None
    if value.get("reason") == "ready" and value.get("running") is True:
        return "ready", value
    if "reason" in value or "running" in value:
        return "starting", value
    return "not_bridge", value


def discover_panel(uuid: str, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    with ThreadPoolExecutor(max_workers=8) as pool:
        while time.monotonic() < deadline:
            candidates = panel_candidates(instance_snapshot(uuid))
            if candidates:
                remaining = max(1, min(8, int(deadline - time.monotonic())))
                results = list(pool.map(lambda url: panel_probe(url, remaining), candidates))
                for candidate, (state, _) in zip(candidates, results):
                    log(f"panel {candidate}: {state}")
                    if state == "ready":
                        return candidate.rstrip("/")
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise ApiError("Timed out discovering a ready H3 bridge panel from the current snapshot")


def boot_instance(uuid: str, timeout: int, panel_timeout: int, inventory_retries: int) -> dict:
    before = instance_status(uuid)
    started_here = before != "running"
    try:
        if before == "shutting_down":
            wait_for_status(uuid, {"shutdown"}, timeout)
            before = "shutdown"
        if before != "running":
            for attempt in range(inventory_retries + 1):
                try:
                    power_on(uuid)
                    break
                except ApiError as exc:
                    if "库存" not in str(exc) or attempt >= inventory_retries:
                        raise
                    delay = min(40, 10 * (attempt + 1))
                    log(f"No inventory; retrying in {delay}s ({attempt + 1}/{inventory_retries})")
                    time.sleep(delay)
            wait_for_status(uuid, {"running"}, timeout)
        panel_url = discover_panel(uuid, panel_timeout)
        return {
            "instance_uuid": uuid,
            "status": "running",
            "panel_url": panel_url,
            "before": before,
            "started_here": started_here,
        }
    except Exception:
        if started_here:
            log("Boot did not complete; powering off the instance started by this command")
            try:
                power_off(uuid)
                wait_for_status(uuid, {"shutdown"}, timeout)
            except Exception as cleanup_error:
                log(f"Cleanup power-off failed: {cleanup_error}")
        raise


def command_list(_: argparse.Namespace) -> None:
    emit({"instances": [instance_summary(item) for item in list_instances()]})


def command_status(args: argparse.Namespace) -> None:
    uuid = resolve_uuid(args)
    emit({"instance_uuid": uuid, "status": instance_status(uuid)})


def command_snapshot(args: argparse.Namespace) -> None:
    uuid = resolve_uuid(args)
    emit({"instance_uuid": uuid, "snapshot": redact(instance_snapshot(uuid))})


def command_on(args: argparse.Namespace) -> None:
    uuid = resolve_uuid(args)
    before = instance_status(uuid)
    if before != "running":
        power_on(uuid)
        if args.wait:
            wait_for_status(uuid, {"running"}, args.timeout)
    emit({"instance_uuid": uuid, "status": instance_status(uuid), "before": before})


def command_off(args: argparse.Namespace) -> None:
    uuid = resolve_uuid(args)
    before = instance_status(uuid)
    if before != "shutdown":
        power_off(uuid)
        if args.wait:
            wait_for_status(uuid, {"shutdown"}, args.timeout)
    emit({"instance_uuid": uuid, "status": instance_status(uuid), "before": before})


def command_boot(args: argparse.Namespace) -> None:
    uuid = resolve_uuid(args)
    emit(boot_instance(uuid, args.timeout, args.panel_timeout, args.inventory_retries))


def add_instance_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--uuid", default="")
    parser.add_argument("--app-hint", default=os.environ.get("AUTODL_APP_HINT", "MINIMAX-H3"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(func=command_list)

    for name, func in (("status", command_status), ("snapshot", command_snapshot)):
        item = subparsers.add_parser(name)
        add_instance_selector(item)
        item.set_defaults(func=func)

    on_parser = subparsers.add_parser("on")
    add_instance_selector(on_parser)
    on_parser.add_argument("--wait", action="store_true")
    on_parser.add_argument("--timeout", type=int, default=900)
    on_parser.set_defaults(func=command_on)

    off_parser = subparsers.add_parser("off")
    add_instance_selector(off_parser)
    off_parser.add_argument("--wait", action="store_true")
    off_parser.add_argument("--timeout", type=int, default=900)
    off_parser.set_defaults(func=command_off)

    boot_parser = subparsers.add_parser("boot")
    add_instance_selector(boot_parser)
    boot_parser.add_argument("--timeout", type=int, default=900)
    boot_parser.add_argument("--panel-timeout", type=int, default=900)
    boot_parser.add_argument("--inventory-retries", type=int, default=2)
    boot_parser.set_defaults(func=command_boot)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.func(args)
        return 0
    except (ApiError, ValueError) as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
