#!/usr/bin/env python3
"""Commands write UTF-8 to a pipe whatever the locale code page is.

Each command runs with PYTHONUTF8=0 and PYTHONIOENCODING=cp1252, so its
streams start in a code page that lacks the fixture text, as an agent's pipe
does on a Windows machine.
"""
from __future__ import annotations

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import smoke_fixtures  # noqa: E402
import stdio_utf8  # noqa: E402

CONFIGURE_FIRST = [ast.dump(ast.parse(line).body[0]) for line in ("import stdio_utf8", "stdio_utf8.configure()")]
SUBPROCESS_CALLS = {"run", "Popen", "check_output", "check_call", "call"}


def run(*arguments: str) -> subprocess.CompletedProcess:
    """Run one product command whose streams start in cp1252, and keep its raw bytes."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
    return subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env, capture_output=True, check=False)


def main_block(tree: ast.Module) -> ast.If | None:
    for node in tree.body:
        test = node.test if isinstance(node, ast.If) else None
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == "__name__"
                and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value == "__main__"):
            return node
    return None


def locale_encoded(call: ast.Call) -> str | None:
    """Name a text-mode file read or write whose encoding is left to the locale code page."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
    owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    if None in keywords:
        return None

    def argument(index: int, keyword: str) -> ast.expr | None:
        return keywords.get(keyword, call.args[index] if len(call.args) > index else None)

    def text(mode: ast.expr | None, default: str = "r") -> bool:
        value = default if mode is None else mode.value if isinstance(mode, ast.Constant) else ""
        return "b" not in value

    if name == "open" and (isinstance(func, ast.Name) or owner in {"io", "codecs"}):
        return "open" if text(argument(1, "mode")) and argument(3, "encoding") is None else None
    if name == "open" and isinstance(func, ast.Attribute):
        mode = call.args[0] if call.args else keywords.get("mode")
        if mode is not None and not (isinstance(mode, ast.Constant) and set(str(mode.value)) <= set("rwxabt+")):
            return None  # ZipFile.open(member), Image.open(path) and os.open(path, flags) take no text mode
        return ".open" if text(mode) and argument(2, "encoding") is None else None
    if name == "read_text":
        return name if argument(0, "encoding") is None else None
    if name == "write_text":
        return name if argument(1, "encoding") is None else None
    if name in {"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}:
        mode = argument(1 if name == "SpooledTemporaryFile" else 0, "mode")
        return name if text(mode, "w+b") and "encoding" not in keywords else None
    if owner == "os" and name == "fdopen":
        return "os.fdopen" if text(argument(1, "mode")) and argument(3, "encoding") is None else None
    if name == "TextIOWrapper":
        return name if argument(1, "encoding") is None else None
    return None


class Streams(unittest.TestCase):
    def configured(self) -> dict[str, io.TextIOWrapper]:
        streams = {name: io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\r\n")
                   for name in ("stdin", "stdout", "stderr")}
        with mock.patch.multiple(sys, **streams):
            stdio_utf8.configure()
        return streams

    def test_stdin_and_stdout_are_strict_utf8_and_keep_their_newlines(self):
        streams = self.configured()
        streams["stdout"].write("Ж\n")
        streams["stdout"].flush()
        self.assertEqual(("utf-8", "strict"), (streams["stdin"].encoding, streams["stdin"].errors))
        self.assertEqual(("utf-8", "strict"), (streams["stdout"].encoding, streams["stdout"].errors))
        self.assertEqual("Ж\r\n".encode("utf-8"), streams["stdout"].buffer.getvalue())

    def test_stderr_escapes_an_undecodable_file_name(self):
        stderr = self.configured()["stderr"]
        # A POSIX file name holding the byte 0xff decodes to this lone surrogate.
        stderr.write("error: cannot read report\udcff.json\n")
        stderr.flush()
        self.assertEqual(("utf-8", "backslashreplace"), (stderr.encoding, stderr.errors))
        self.assertEqual(b"error: cannot read report\\udcff.json\r\n", stderr.buffer.getvalue())


class Commands(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="cpb-stdio-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_studio_init_prints_a_title_outside_the_code_page(self):
        done = run("scripts/studio.py", "init", "--out", str(self.work / "studio"),
                   "--studio-id", "enc-probe", "--title", "𠮷 studio")
        self.assertEqual(0, done.returncode, done.stderr.decode("utf-8", "replace"))
        self.assertIn("𠮷 studio", done.stdout.decode("utf-8"))
        self.assertTrue(done.stdout.endswith(os.linesep.encode("ascii")), done.stdout)

    def test_narrative_init_prints_json_naming_a_folder_outside_the_code_page(self):
        out = self.work / "연재"
        done = run("scripts/narrative_init.py", "--out", str(out), "--series-id", "enc-series", "--title", "Encoding probe")
        self.assertEqual(0, done.returncode, done.stderr.decode("utf-8", "replace"))
        self.assertEqual(out.name, Path(json.loads(done.stdout.decode("utf-8"))["series"]).name)

    def test_a_refusal_names_a_folder_outside_the_code_page(self):
        folder = self.work / "角色设计"
        folder.mkdir()
        done = run("scripts/studio.py", "--studio", str(folder), "status")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn(folder.name, done.stderr.decode("utf-8"))


class Sources(unittest.TestCase):
    def test_every_command_configures_its_streams_first(self):
        commands, unconfigured = [], []
        for path in sorted([*ROOT.glob("scripts/*.py"), *ROOT.glob("examples/*/*.py")]):
            block = main_block(ast.parse(path.read_text(encoding="utf-8")))
            if block is None:
                continue
            commands.append(path.name)
            if [ast.dump(statement) for statement in block.body[:2]] != CONFIGURE_FIRST:
                unconfigured.append(path.relative_to(ROOT).as_posix())
        self.assertIn("studio.py", commands)
        self.assertEqual([], unconfigured)

    def test_every_subprocess_read_as_text_decodes_utf8(self):
        calls, undeclared = 0, []
        for path in sorted([*ROOT.glob("scripts/*.py"), *ROOT.glob("examples/*/*.py"), *ROOT.glob("tests/*.py")]):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in SUBPROCESS_CALLS and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"):
                    continue
                keywords = {keyword.arg: keyword.value for keyword in node.keywords}
                textual = [keywords[key] for key in ("text", "universal_newlines") if key in keywords]
                if not any(not (isinstance(value, ast.Constant) and value.value is False) for value in textual):
                    continue
                calls += 1
                encoding = keywords.get("encoding")
                if not (isinstance(encoding, ast.Constant) and encoding.value == "utf-8"):
                    undeclared.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
        self.assertTrue(calls)
        self.assertEqual([], undeclared)

    def test_every_text_file_read_and_write_names_its_encoding(self):
        undeclared = []
        for path in sorted([*ROOT.glob("scripts/*.py"), *ROOT.glob("examples/*/*.py"), *ROOT.glob("tests/*.py")]):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                kind = locale_encoded(node) if isinstance(node, ast.Call) else None
                if kind:
                    undeclared.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: {kind}")
        self.assertEqual([], undeclared)

    def test_the_file_check_finds_each_locale_encoded_form(self):
        found = [locale_encoded(node) for node in ast.walk(ast.parse(
            "open(p); open(p, 'a'); p.open(); p.open('w'); p.read_text(); p.write_text(s)\n"
            "tempfile.NamedTemporaryFile('w'); os.fdopen(d, 'w'); io.TextIOWrapper(b)\n"
            "open(p, 'rb'); p.open('rb'); p.read_text('utf-8'); p.write_text(s, encoding='utf-8')\n"
            "zipfile.ZipFile(p).open('member.json'); tarfile.open(p, 'r:gz'); tempfile.TemporaryFile()\n"
        )) if isinstance(node, ast.Call)]
        self.assertEqual(["open", "open", ".open", ".open", "read_text", "write_text",
                          "NamedTemporaryFile", "os.fdopen", "TextIOWrapper"], [kind for kind in found if kind])


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    smoke_fixtures.isolate_home()
    unittest.main(verbosity=2)
