"""Build executable Python commands and display their complete argument vectors."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def python_argv(script: str | Path, *arguments: str) -> list[str]:
    """Keep the running interpreter, including its virtual environment, and an absolute script path."""
    # Resolving the executable's symlink would select the base Python outside a venv.
    return [os.path.abspath(sys.executable), str(Path(script).resolve()), *arguments]


def shown(arguments: Sequence[str]) -> str:
    """Quote a complete command for the platform's command-line convention."""
    return subprocess.list2cmdline(list(arguments)) if os.name == "nt" else shlex.join(arguments)
