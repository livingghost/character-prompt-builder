#!/usr/bin/env python3
"""Exercise the product README's offline commands, not its prose quality.

Only the explicitly marked local examples are executed. Live send examples are
checked against CLI help and for required authority arguments, never sent. These
checks establish executable documentation, not creative or real-model quality.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

REPOSITORY = Path(__file__).resolve().parents[1]
SUITE = Path(__file__).resolve().parents[1]
EXAMPLES = {"production-lifecycle", "core-check", "public-exchange", "authoring-material"}
SEND_EXAMPLES = {"upscale", "generation"}
SEND_FLAGS = ["--production-root", "--production-run", "--production-authorization", "--send"]
OFFLINE_SCRIPTS = {
    "scripts/scene_persona.py",
    "examples/production-execution/run_example.py",
    "scripts/protocol_exchange.py",
    "scripts/check_dependencies.py",
    "scripts/create_authoring_example.py",
    "scripts/source_material.py",
}
OUTPUTS = {"../cpb-authoring-demo": "authoring", "../cpb-production-demo": "production"}


def blocks(text: str, marker: str) -> dict[str, str]:
    pattern = (
        r"<!-- " + re.escape(marker) + r": ([a-z-]+) -->\s*"
        r"```sh\n(.*?)\n```\s*<!-- end-" + re.escape(marker) + r" -->"
    )
    result: dict[str, str] = {}
    for name, content in re.findall(pattern, text, re.S):
        if name in result:
            raise ValueError(f"duplicate documented example: {name}")
        result[name] = content
    if len(re.findall(r"<!-- " + re.escape(marker) + r":", text)) != len(result):
        raise ValueError(f"malformed {marker} block")
    return result


def send_errors(tokens: list[str]) -> list[str]:
    return [
        f"missing required live-send argument: {flag}" for flag in SEND_FLAGS if flag not in tokens
    ]


def structure_errors(text: str) -> list[str]:
    """Check distinct governance sections without imposing a prose-size budget.

    This checks document structure and original destinations, not readability or
    adequacy of the rest of the README. Those still need editorial review.
    """
    sections: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    current = None
    fence_character = None
    fence_length = 0
    for line in text.splitlines():
        opening = re.match(r"^\s*(`{3,}|~{3,})", line)
        if opening:
            mark = opening.group(1)
            if fence_character is None:
                fence_character, fence_length = mark[0], len(mark)
            elif mark[0] == fence_character and len(mark) >= fence_length:
                fence_character = None
            continue
        if fence_character is not None:
            continue
        heading = re.match(r"^## ([^#].*?)\s*$", line)
        if heading:
            current = heading.group(1)
            counts[current] = counts.get(current, 0) + 1
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)

    errors = []
    for title in ("Contributing", "License", "Support"):
        if counts.get(title, 0) != 1:
            errors.append(f"{title} must have its own unique section")
            continue
        body = "\n".join(sections[title])
        prose = re.sub(r"\[[^\]]*\]\([^)]*\)", "", body)
        prose = re.sub(r"https?://\S+", "", prose)
        prose = re.sub(r"^#+.*$", "", prose, flags=re.M)
        if not re.search(r"[A-Za-z]{2,}", prose):
            errors.append(f"{title} must explain its purpose, not only list links")
    if "[CONTRIBUTING.md](CONTRIBUTING.md)" not in "\n".join(sections.get("Contributing", [])):
        errors.append("Contributing must retain the contributor-guide destination")
    license_body = "\n".join(sections.get("License", []))
    if "GNU GPLv3" not in license_body or "[LICENSE](LICENSE)" not in license_body:
        errors.append("License must retain the original license designation and file")
    if "https://github.com/sponsors/livingghost" not in "\n".join(sections.get("Support", [])):
        errors.append("Support must retain the original development-support destination")
    return errors


def introduction_errors(text: str) -> list[str]:
    """Check retained explanatory anchors/order, not a word budget or writing quality."""
    errors = []
    installation = re.search(r"^## Installation\s*$", text, re.M)
    for heading in ("Who this project is for", "Core production chain"):
        match = re.search(r"^## " + re.escape(heading) + r"\s*$", text, re.M)
        if match is None:
            errors.append("missing project explanation: " + heading)
        elif installation and match.start() > installation.start():
            errors.append("project explanation must precede installation: " + heading)
    return errors


def main() -> int:
    checks: list[dict] = []
    commands: list[dict] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(passed), "detail": detail})

    def invoke(argv: list[str], env: dict, *, expected: int = 0) -> subprocess.CompletedProcess:
        result = subprocess.run(
            argv,
            cwd=REPOSITORY,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
            check=False,
        )
        commands.append(
            {
                "argv": argv,
                "returncode": result.returncode,
                "expected_returncode": expected,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != expected:
            raise ValueError(f"documented command failed: {argv}\n{result.stdout}\n{result.stderr}")
        return result

    try:
        text = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        check("purpose and creative flow precede installation", not introduction_errors(text), "; ".join(introduction_errors(text)))
        for heading in ("Who this project is for", "Core production chain"):
            check("missing introduction detected: " + heading, bool(introduction_errors(text.replace("## " + heading, "## Removed explanation"))))
        check(
            "independent governance sections with retained destinations",
            not structure_errors(text),
            "; ".join(structure_errors(text)),
        )
        merged = text.replace("## Contributing\n", "## Contributing, license and support\n")
        check("merged governance sections are rejected", bool(structure_errors(merged)))
        for title in ("Contributing", "License", "Support"):
            missing = text.replace("## " + title + "\n", "## Other " + title + "\n")
            check("missing independent section rejected: " + title, bool(structure_errors(missing)))
        long_prose = text + "\n" + ("Additional substantive explanation. " * 4000)
        check("documentation is not rejected for length", not structure_errors(long_prose))
        links = re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", text)
        for link in links:
            value = urlsplit(link)
            if value.scheme or value.netloc or not value.path:
                continue
            target = (REPOSITORY / unquote(value.path)).resolve()
            check(f"local link: {link}", target.is_relative_to(REPOSITORY) and target.exists())
        examples = blocks(text, "readme-example")
        check("offline example inventory", set(examples) == EXAMPLES)
        if set(examples) != EXAMPLES:
            raise ValueError("README offline example set is incomplete or unexpected")
        sends = blocks(text, "readme-send")
        check("live example inventory", set(sends) == SEND_EXAMPLES)
        for name, content in sends.items():
            tokens = shlex.split(content)
            check(f"live send arguments: {name}", not send_errors(tokens))
            for flag in SEND_FLAGS:
                removed = [token for token in tokens if token != flag]
                check(f"missing {flag} rejected: {name}", bool(send_errors(removed)))
        with tempfile.TemporaryDirectory(prefix="readme workspace ") as temporary:
            temp = Path(temporary)
            home = temp / "home"
            home.mkdir()
            env = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "NO_COLOR": "1",
                "PYTHON_COLORS": "0",
                "HOME": str(home),
                "USERPROFILE": str(home),
            }
            mapping = {key: str(temp / value) for key, value in OUTPUTS.items()}
            for name, content in examples.items():
                for line in content.splitlines():
                    if not line.strip():
                        continue
                    tokens = shlex.split(line)
                    if len(tokens) < 2 or tokens[0] != "python" or tokens[1] not in OFFLINE_SCRIPTS:
                        raise ValueError(f"unapproved offline example command: {line}")
                    if "--send" in tokens:
                        raise ValueError("live send cannot be an offline example")
                    argv = [sys.executable, "-B", *[mapping.get(t, t) for t in tokens[1:]]]
                    invoke(argv, env)
                check(f"offline example executed: {name}", True)
            authoring = temp / "authoring"
            for relative in (
                "scene-material/persona.md",
                "scene-material/material.json",
                "source-material/index.json",
                "extraction-proposal/proposal.json",
            ):
                check(f"documented output exists: {relative}", (authoring / relative).is_file())
            material = json.loads((authoring / "scene-material/material.json").read_text())
            check(
                "scene material is the public artifact",
                material.get("artifact_type") == "scene-persona-material",
            )
            index = json.loads((authoring / "source-material/index.json").read_text())
            check("source intake does not adopt canon", index.get("canon_adopted") is False)
            completed = json.loads((temp / "production/result.json").read_text())
            check("text production example completes", completed.get("ok") is True)
            check(
                "production result is identified as synthetic",
                completed.get("fixture_only") is True,
            )
            original = authoring / "originals/subject.md"
            saved = original.read_bytes()
            try:
                original.write_bytes(saved + b"\nA new, unquoted condition.\n")
                invoke(
                    [
                        sys.executable,
                        "-B",
                        str(SUITE / "scripts/scene_persona.py"),
                        "verify",
                        "--root",
                        str(authoring),
                        "--plan",
                        "scene-plan.json",
                        "--bundle",
                        "scene-material",
                        "--require-ready",
                    ],
                    env,
                    expected=1,
                )
                check("an unquoted source change invalidates scene reuse", True)
                invoke(
                    [
                        sys.executable,
                        "-B",
                        str(SUITE / "scripts/source_material.py"),
                        "verify",
                        "--root",
                        str(authoring),
                        "--bundle",
                        "source-material",
                    ],
                    env,
                )
                check("archived source bytes remain verifiable", True)
            finally:
                original.write_bytes(saved)
            help_result = invoke(
                [sys.executable, "-B", str(SUITE / "scripts/dispatch.py"), "--help"], env
            )
            for name, content in sends.items():
                flags = {token for token in shlex.split(content) if token.startswith("--")}
                check(
                    f"live example options exist in dispatcher: {name}",
                    all(flag in help_result.stdout for flag in flags),
                )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        check("README execution", False, str(exc))
    ok = all(row["ok"] for row in checks) and bool(checks)
    print(
        json.dumps(
            {
                "ok": ok,
                "checks": len(checks),
                "details": checks,
                "commands": commands,
                "limits": "Offline fixtures and CLI signatures only; no provider, real-agent or prose-quality assessment.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
