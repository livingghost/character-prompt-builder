"""Explicitly synthetic retrieval data for offline smoke tests, never production defaults."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from typing import Any, Callable
from prompt_retrieval import settle_retrieval_record


def fixture_retrieval(prompt: str, plot: dict[str, Any]) -> dict[str, Any]:
    return settle_retrieval_record({"artifact_type": "prompt-retrieval-record", "pack_state": "offline-test-fixture",
        "elements": [{"element": "offline fixture composition", "queries": ["offline fixture lookup"],
                      "inspected_records": [], "outcome": "composed", "composed_wording": prompt.strip(),
                      "reason": "Synthetic test data, not a claim that a production search was performed."}]},
        prompt=prompt, plot=plot)


def cli_with_fixture_retrieval(main: Callable[..., Any], argv: list[str]) -> Any:
    """Adapt pre-existing CLI scenario inputs to the new explicit required input."""
    if "--retrieval-record-file" in argv:
        return main(argv)
    with tempfile.TemporaryDirectory(prefix="cpb-test-retrieval-") as temp:
        path = Path(temp) / "retrieval.json"
        prompt_path = Path(argv[argv.index("--prompt-file") + 1])
        plot_path = Path(argv[argv.index("--plot-file") + 1])
        # Keep the newly required fixture input present even in old scenarios
        # intentionally missing another input. Do not mask that input's error.
        value = {"artifact_type": "prompt-retrieval-record", "settled": False,
                 "elements": [{"element": "offline missing-input fixture", "queries": ["synthetic lookup"],
                   "inspected_records": [], "outcome": "composed", "composed_wording": "synthetic",
                   "reason": "This fixture tests an intentionally absent input, not production retrieval."}]}
        if prompt_path.is_file() and plot_path.is_file():
            value = fixture_retrieval(prompt_path.read_text(encoding="utf-8"), json.loads(plot_path.read_text(encoding="utf-8")))
        path.write_text(json.dumps(value), encoding="utf-8")
        return main([*argv, "--retrieval-record-file", str(path)])
