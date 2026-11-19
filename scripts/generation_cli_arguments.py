"""Prepared-run inputs and avoidance transport choices shared by package builders."""
from __future__ import annotations
import argparse
from pathlib import Path

TRANSPORT_MODES = {
    "auto",
    "separate-field",
    "integrated-critical",
    "native-subset",
    "retained-only",
}

def add_production_arguments(parser: argparse.ArgumentParser) -> None:
    """Name the prepared run and the decisions a builder cannot derive from it."""
    parser.add_argument("--production-root", type=Path, required=True,
                        help="Studio root holding the prepared production run and the studio's input evidence; "
                        "every relative file argument is a /-separated path below it")
    parser.add_argument("--production-run", help="Prepared run; the open work task's current run when omitted")
    parser.add_argument("--request-validation-file",
                        help="Request check with its own evidence and execution policy; when omitted, the builder "
                        "derives it from the selected parameter schema the active pack's offering names")
    parser.add_argument("--visual-continuity-file",
                        help="Complete visual continuity record; when omitted, --continuity states the decisions")
    parser.add_argument("--continuity", action="append", default=[], metavar="SUBJECT=DECISION",
                        help="once for each production subject: one-off; undecided for the first images of a "
                        "character that may recur; recurring once the author has accepted an identity image")
    parser.add_argument("--character", action="append", default=[], metavar="SUBJECT=CHARACTER",
                        help="The studio character a subject is recorded under; required for a recurring subject")
    parser.add_argument("--sheet-panel", action="store_true", help="The image fills a character sheet panel")
