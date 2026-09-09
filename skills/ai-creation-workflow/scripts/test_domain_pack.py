#!/usr/bin/env python3
"""Focused domain-pack regression tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import domain_pack


def main() -> int:
    assert domain_pack.validate_all(domain_pack.PACK_ROOT) == 0
    packs = {path.parent.name: json.loads(path.read_text(encoding="utf-8")) for path in domain_pack.pack_paths(domain_pack.PACK_ROOT)}
    assert "ai-video" in packs
    assert "longform-writing" in packs
    text = json.dumps(packs["longform-writing"], ensure_ascii=False).casefold()
    assert "h3" not in text and "comfyui" not in text
    installed_names = {"h3-runtime-router", "comfyui-local-runner", "minimax-h3-cloud"}
    assert installed_names.isdisjoint(packs["ai-video"]["runtime_adapters"])
    with tempfile.TemporaryDirectory(prefix="domain-pack-") as raw:
        root = Path(raw)
        (root / "guide.md").write_text("# Guide\n", encoding="utf-8")
        invalid = json.loads(json.dumps(packs["longform-writing"]))
        invalid["guide"] = "guide.md"
        invalid["stage_templates"][0]["optional"] = True
        path = root / "longform-writing" / "pack.json"
        path.parent.mkdir()
        path.write_text(json.dumps(invalid), encoding="utf-8")
        errors = domain_pack.validate_pack(path, root)
        assert any("depends on optional stage" in error for error in errors)
    print("Domain pack tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
