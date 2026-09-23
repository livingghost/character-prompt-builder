#!/usr/bin/env python3
"""Select state-valid reference assets from explicit state-aware bindings."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from catalog_cli import configure_pack_runtime
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
from state_protocol import (
    artifact_hash,
    load_json,
    select_state_references,
    validate_artifact,
    write_json,
)


def _checked_artifact(path_value: str | None, expected_type: str) -> dict[str, Any] | None:
    if not path_value:
        return None
    artifact = load_json(Path(path_value))
    if artifact.get("artifact_type") != expected_type:
        raise ValueError(
            f"expected artifact_type {expected_type}, got {artifact.get('artifact_type')}: {path_value}"
        )
    report = validate_artifact(artifact)
    if not report.get("ok"):
        raise ValueError(f"invalid {expected_type}: " + "; ".join(report.get("errors", [])))
    return artifact


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select state-aware reference assets.")
    parser.add_argument("--bindings", required=True)
    parser.add_argument("--selection-id", required=True)
    parser.add_argument("--identity-contract", required=True)
    parser.add_argument("--era-contract")
    parser.add_argument("--appearance-variant")
    parser.add_argument("--state-snapshot")
    parser.add_argument("--story-order", required=True, type=int)
    parser.add_argument("--required-feature", action="append", default=[])
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--out", required=True)
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        raw = json.loads(Path(args.bindings).read_text(encoding="utf-8"))
        bindings = raw.get("bindings", []) if isinstance(raw, dict) else raw
        if not isinstance(bindings, list) or not all(isinstance(item, dict) for item in bindings):
            raise ValueError("bindings file must be an array or an object containing a bindings array")

        identity = _checked_artifact(args.identity_contract, "character-identity-contract")
        assert identity is not None
        identity_hash = artifact_hash(identity)
        character_id = str(identity.get("character_id") or "")
        era = _checked_artifact(args.era_contract, "era-contract")
        appearance = _checked_artifact(args.appearance_variant, "appearance-variant-contract")
        state = _checked_artifact(args.state_snapshot, "state-snapshot")

        for name, artifact in (("era contract", era), ("appearance variant", appearance)):
            if artifact is None:
                continue
            if artifact.get("character_id") != character_id:
                raise ValueError(f"{name} belongs to another character")
            if artifact.get("parent_identity_contract_sha256") != identity_hash:
                raise ValueError(f"{name} parent identity hash differs from the supplied identity")
        if state is not None:
            if state.get("character_id") != character_id:
                raise ValueError("state snapshot belongs to another character")
            if state.get("identity_contract_sha256") != identity_hash:
                raise ValueError("state snapshot identity hash differs from the supplied identity")
            if state.get("era_contract_sha256") != (artifact_hash(era) if era else None):
                raise ValueError("state snapshot era hash differs from the supplied era contract")
            if state.get("appearance_variant_sha256") != (
                artifact_hash(appearance) if appearance else None
            ):
                raise ValueError(
                    "state snapshot appearance hash differs from the supplied appearance variant"
                )

        value = select_state_references(
            bindings=bindings,
            selection_id=args.selection_id,
            identity_hash=identity_hash,
            era_hash=artifact_hash(era) if era else None,
            appearance_hash=artifact_hash(appearance) if appearance else None,
            state_hash=artifact_hash(state) if state else None,
            story_order=args.story_order,
            required_features=args.required_feature,
            limit=args.limit,
        )
        report = validate_artifact(value)
        if not report.get("ok"):
            raise ValueError("invalid reference selection: " + "; ".join(report.get("errors", [])))
        write_json(Path(args.out), value)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, TypeError, AttributeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
