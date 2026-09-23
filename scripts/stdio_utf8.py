#!/usr/bin/env python3
"""Set a command's standard streams to UTF-8 whatever the locale code page is.

A command whose output goes to a pipe otherwise encodes it with the locale
code page. That garbles text outside the page or ends the command after its
work is saved. Every command calls configure() first in its ``__main__`` block.
"""
from __future__ import annotations

import sys


def configure() -> None:
    """Reconfigure the standard streams to UTF-8 and keep their newline handling.

    stdin and stdout are strict. stderr escapes what UTF-8 cannot encode, such
    as an undecodable file name, so reporting an error never fails itself. A
    stream that is absent or offers no reconfigure() stays as it is.
    """
    for stream, errors in ((sys.stdin, "strict"), (sys.stdout, "strict"), (sys.stderr, "backslashreplace")):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors=errors)
