#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Static lexical size only. This neither measures host tokens nor establishes
# whether selecting fewer files preserves the task's meaning.
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=Path, default=ROOT / "config/runtime-read-routes.json")
    args = parser.parse_args()
    routes = json.loads(args.routes.read_text(encoding="utf-8"))
    report = {"ok": True, "measurement": "static-lexical-words-not-host-tokens", "routes": {}}
    from execution_routes import resolve
    for name, scenario in routes.items():
        files = [entry["path"] for entry in resolve(scenario["route"], scenario["features"])["reads"]]
        total = 0
        parts = []
        for rel in files:
            path = ROOT / rel
            if not path.is_file():
                report["ok"] = False
                parts.append({"path": rel, "missing": True, "words": 0})
                continue
            words = count_words(path.read_text(encoding="utf-8"))
            total += words
            entry = {"path": rel, "missing": False, "words": words}
            parts.append(entry)
        report["routes"][name] = {"words": total, "files": parts}
    report["errors"] = [] if report["ok"] else ["one or more route files are missing"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
