#!/usr/bin/env python3
"""Verify that public lock publication preserves UUID/CalVer immutability."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pack_manager import write_lock

ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "0190c000-0000-7000-8000-000000000088"
EXPECTED_CHECKS = 9


def run_cli(pack: Path) -> tuple[int, dict[str, Any]]:
    process = subprocess.run(
        [sys.executable, "scripts/pack_cli.py", "build-lock", str(pack)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
        env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"pack_cli did not emit JSON: stdout={process.stdout!r} stderr={process.stderr!r}"
        ) from exc
    return process.returncode, value


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory(prefix="cpb-pack-release-identity-") as raw:
        root = Path(raw).resolve()
        pack = root / "pack"
        shutil.copytree(ROOT / "packs/commons", pack)
        (pack / "pack.lock.json").unlink(missing_ok=True)
        manifest_path = pack / "pack.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["pack_id"] = PACK_ID
        manifest["release"] = "2026.08.24.1"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        rc, first = run_cli(pack)
        check("first public lock publication succeeds", rc == 0 and first.get("ok") is True, first)
        lock_path = pack / "pack.lock.json"
        first_bytes = lock_path.read_bytes()
        first_lock = json.loads(first_bytes)
        check("published lock records the requested identity", first_lock["pack_id"] == PACK_ID and first_lock["release"] == "2026.08.24.1")

        rc, second = run_cli(pack)
        check("idempotent publication succeeds", rc == 0 and second.get("ok") is True, second)
        check("idempotent publication is byte-identical", lock_path.read_bytes() == first_bytes)

        models_path = pack / "records/models.json"
        models = json.loads(models_path.read_text(encoding="utf-8"))
        models["records"][0]["label"] += " changed"
        models_path.write_text(
            json.dumps(models, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        rc, rejected = run_cli(pack)
        check("changed bytes under the same release are rejected", rc == 2 and rejected.get("ok") is False, rejected)
        check("rejection explains the immutable release rule", "Increment pack.json release" in str(rejected.get("error")), rejected)
        check("rejected publication leaves the existing lock untouched", lock_path.read_bytes() == first_bytes)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["release"] = "2026.08.24.2"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        rc, bumped = run_cli(pack)
        check("a new release can publish changed bytes", rc == 0 and bumped.get("release") == "2026.08.24.2", bumped)

        fixture = root / "development-fixture"
        shutil.copytree(pack, fixture)
        fixture_models_path = fixture / "records/models.json"
        fixture_models = json.loads(fixture_models_path.read_text(encoding="utf-8"))
        fixture_models["records"][0]["label"] += " fixture"
        fixture_models_path.write_text(
            json.dumps(fixture_models, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        direct = write_lock(fixture)
        check("low-level fixture lock rewrites remain available", direct["release"] == "2026.08.24.2")

    report = {
        "ok": len(results) == EXPECTED_CHECKS and all(row["passed"] for row in results),
        "checks": len(results),
        "expected_checks": EXPECTED_CHECKS,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
