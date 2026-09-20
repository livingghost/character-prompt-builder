#!/usr/bin/env python3
"""Prove the Full builder runs and enforces each bundled Pack's actual gate."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from pack_manager import initialize_pack, write_lock
from package_full import run_bundled_pack_release_gates

EXPECTED_CHECKS = 8

FAKE_GATE = r'''#!/usr/bin/env python3
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('pack', type=Path)
p.add_argument('--state-file', type=Path, required=True)
p.add_argument('--cache-dir', type=Path, required=True)
p.add_argument('--managed-root', type=Path, required=True)
p.add_argument('--report-out', type=Path, required=True)
a=p.parse_args()
manifest=json.loads((a.pack/'pack.json').read_text(encoding='utf-8'))
state=json.loads(a.state_file.read_text(encoding='utf-8'))
exact=(state.get('enabled_packs') == [manifest['pack_id']] and state.get('pack_roots') == [str(a.pack.resolve())])
forced=(a.pack/'FAIL-GATE').exists()
value={'ok': bool(exact and not forced), 'suites': [{'id':'fixture','ok':bool(exact and not forced)}], 'observed_state':state}
a.report_out.parent.mkdir(parents=True, exist_ok=True)
a.report_out.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
print(json.dumps(value))
raise SystemExit(0 if value['ok'] else 1)
'''


def main() -> int:
    rows: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        rows.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory(prefix="cpb-bundled-pack-gate-") as temp_name:
        root = Path(temp_name).resolve()
        scripts = root / "scripts"
        scripts.mkdir()
        gate = scripts / "pack_release_gate.py"
        gate.write_text(FAKE_GATE, encoding="utf-8", newline="\n")

        pack_ids: list[str] = []
        for index in (1, 2):
            pack = root / "packs" / f"pack-{index}"
            manifest = initialize_pack(pack, name=f"Pack {index}", release=f"2026.08.24.{index}")
            (pack / "notice.txt").write_text(f"pack {index} fixture\n", encoding="utf-8", newline="\n")
            manifest["content"]["resource_globs"] = ["*.txt"]
            (pack / "pack.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            write_lock(pack)
            pack_ids.append(manifest["pack_id"])

        reports = root / "reports"
        reports.mkdir()
        result = run_bundled_pack_release_gates(
            root,
            label="fixture",
            reports_dir=reports,
            runtime_root=root / "runtime-pass",
        )
        check("helper reports success only after every Pack gate runs", result["ok"] is True)
        check("both bundled Packs are gated", result["pack_count"] == 2 and result["checks"] == 2)
        check("each Pack result is retained", len(result["packs"]) == 2)
        check("each isolated state enables exactly one Pack", all(len(row.get("suite_results") or []) == 1 for row in result["packs"]))
        check("aggregate gate report is persisted", (reports / "fixture-bundled-pack-gates.json").is_file())
        check("per-Pack reports are persisted", all((reports / f"fixture-pack-gate-{pack_id}.json").is_file() for pack_id in pack_ids))

        failing_pack = root / "packs" / "pack-2"
        (failing_pack / "FAIL-GATE").write_text("fail\n", encoding="utf-8")
        write_lock(failing_pack)
        try:
            run_bundled_pack_release_gates(
                root,
                label="failure",
                reports_dir=reports,
                runtime_root=root / "runtime-fail",
            )
        except RuntimeError as exc:
            blocked = "failed" in str(exc)
        else:
            blocked = False
        check("one failed Pack gate blocks the Full builder", blocked)
        failure_report = json.loads((reports / "failure-bundled-pack-gates.json").read_text(encoding="utf-8"))
        check("failure report names the failed release boundary", failure_report["ok"] is False and bool(failure_report["errors"]))

    report = {
        "ok": len(rows) == EXPECTED_CHECKS and all(row["passed"] for row in rows),
        "checks": len(rows),
        "expected_checks": EXPECTED_CHECKS,
        "results": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
