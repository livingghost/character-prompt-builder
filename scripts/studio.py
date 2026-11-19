#!/usr/bin/env python3
"""A studio: where one body of character work lives, with its trail.

A studio holds characters, each with its sheet, every image ever generated for
it, and which of those images are accepted for which slot. Every generation is
an iteration: the exact request that was sent, what came back, the file, and the
package it was built from, so that an image can be regenerated later with the
same settings and a quality that drifted can be traced to what changed. An
accepted image is superseded, never overwritten, when the owner changes their
mind, and every acceptance is kept with its time, so the history of a slot is
readable end to end.

The studio also carries the open task and the trail of tasks (see
work_ledger.py), so a session that lost its context reads where the work stands
and continues.

    python scripts/studio.py init --out DIR --studio-id ID --title "..."
    python scripts/studio.py status --studio DIR
    python scripts/studio.py character add <id> --studio DIR [--profile general|humanoid|anthro|<path>]
    python scripts/studio.py iterate --studio DIR --character <id> --slot <slot> --result <file>
        [--package <file>] [--package-companion <dir>] [--request <file>] [--response <file>] [--note "..."]
    python scripts/studio.py attach-package --studio DIR --character <id> --iteration <it-id>
        --package <file> [--package-companion <dir>] --evidence <file> --actor "..." --reason "..."
    python scripts/studio.py accept --studio DIR --character <id> --iteration <it-id>
    python scripts/studio.py reject --studio DIR --character <id> --iteration <it-id> --reason "..." --actor "..."
    python scripts/studio.py recipe --studio DIR --character <id> --slot <slot> [--iteration <it-id>]
    python scripts/studio.py gallery --studio DIR [--out <file.html>]
    python scripts/studio.py credentials prepare SERVICE --studio DIR
        [--environment NAME | --stored]
    python scripts/studio.py credentials set SERVICE --studio DIR [--stdin | --from-env NAME]
    python scripts/studio.py credentials status [SERVICE] --studio DIR
    python scripts/studio.py credentials remove SERVICE --studio DIR

`--studio` names any directory in the studio, before or after the command, and
defaults to the working directory.
"""
from __future__ import annotations
import operation_context as _operation_context
import argparse


import json


import sys


from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--studio", type=Path, default=None, help="A directory in the studio (default: the working directory)")
    # The studio may also be named after the command, as the documentation writes it.
    after = _operation_context.ArgumentParser(add_help=False)
    after.add_argument("--studio", type=Path, default=argparse.SUPPRESS,
                       help="A directory in the studio (default: the working directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="create a studio")
    init_parser.add_argument("--out", type=Path, required=True)
    init_parser.add_argument("--studio-id", required=True)
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--default-render-profile",
                             help="a selected project render-profile preference (default: unselected)")
    init_parser.add_argument("--default-creative-latitude", default="directed")
    init_parser.add_argument("--default-interaction-mode", default="balanced")
    init_parser.add_argument("--default-style-family", help="a selected project style-family preference (default: unselected)")
    commands.add_parser("status", help="check the open task, current slots and waiting candidates; sync checks historical displays",
                       description="Verify current slots, waiting candidates and canonical references. Repair their displays; "
                       "retain historical gallery entries from the last publication. Use sync for a full historical source check.",
                       parents=[after])
    auth_parser = commands.add_parser("credentials", help="manage one saved API key or environment source per service", parents=[after])
    auth_commands = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_prepare = auth_commands.add_parser("prepare", parents=[after],
        help="prepare the service's API-key entry or select its environment variable",
        description="Prepare one authentication entry for the service in credentials.json. Existing values and environment sources are retained by default. Give the owner the returned file path and JSON Pointer to fill the API-key string and save. Use --environment or --stored to explicitly change the service's source.")
    auth_prepare.add_argument("service", metavar="SERVICE", help="the service identifier selected by the model offering")
    auth_source = auth_prepare.add_mutually_exclusive_group()
    auth_source.add_argument("--environment", metavar="NAME", help="read this process environment variable whenever execution needs authentication")
    auth_source.add_argument("--stored", action="store_true", help="select the service's api_key string; retain its saved value or prepare an empty string")
    auth_set = auth_commands.add_parser("set", parents=[after],
        help="save or rotate a private value for a service; hidden terminal input is the default")
    auth_set.add_argument("service", metavar="SERVICE", help="the service identifier selected by the model offering")
    auth_input = auth_set.add_mutually_exclusive_group()
    auth_input.add_argument("--stdin", action="store_true", help="read the complete value from standard input without trimming whitespace")
    auth_input.add_argument("--from-env", metavar="NAME", help="import this environment variable's current value into private storage")
    auth_status = auth_commands.add_parser("status", parents=[after],
        help="show each service's authentication source and local availability")
    auth_status.add_argument("service", metavar="SERVICE", nargs="?")
    auth_remove = auth_commands.add_parser("remove", parents=[after],
        help="remove the service's saved key or environment reference from this Studio")
    auth_remove.add_argument("service", metavar="SERVICE")
    character_parser = commands.add_parser("character", help="characters")
    character_commands = character_parser.add_subparsers(dest="character_command", required=True)
    add_parser = character_commands.add_parser("add", help="add a character with a blank sheet", parents=[after])
    add_parser.add_argument("character")
    add_parser.add_argument("--profile", default="")
    iterate_parser = commands.add_parser("iterate", help="record one generated image with what produced it", parents=[after])
    iterate_parser.add_argument("--character", required=True)
    iterate_parser.add_argument("--slot", required=True)
    iterate_parser.add_argument("--result", type=Path, required=True)
    iterate_parser.add_argument("--package", type=Path)
    iterate_parser.add_argument("--package-companion", type=Path, help="the saved package companion directory, kept under its exact name")
    iterate_parser.add_argument("--request", type=Path, help="the request as sent, JSON")
    iterate_parser.add_argument("--response", type=Path, help="what the service answered, JSON")
    iterate_parser.add_argument("--note")
    attach_parser = commands.add_parser("attach-package", parents=[after],
        help="record an imported iteration's original Generation Package with later attribution evidence")
    attach_parser.add_argument("--character", required=True)
    attach_parser.add_argument("--iteration", required=True)
    attach_parser.add_argument("--package", type=Path, required=True)
    attach_parser.add_argument("--package-companion", type=Path,
        help="the original .references directory, discovered beside the package when omitted")
    attach_parser.add_argument("--evidence", type=Path, required=True,
        help="existing evidence relating this package to the exact imported image; retained with the attribution")
    attach_parser.add_argument("--actor", required=True, help="Actual person or agent making the attribution")
    attach_parser.add_argument("--reason", required=True, help="Why the evidence establishes this image's original input package")
    accept_parser = commands.add_parser("accept", help="accept an iteration for its slot; the previous one is superseded", parents=[after])
    accept_parser.add_argument("--character", required=True)
    accept_parser.add_argument("--iteration", required=True)
    placement_draft = commands.add_parser('draft-reassignment', parents=[after],
        help='draft an exact source/destination correction for one retained iteration')
    placement_draft.add_argument('--character', required=True)
    placement_draft.add_argument('--iteration', required=True)
    placement_draft.add_argument('--slot', required=True, help='the intended current destination; original recording stays unchanged')
    placement_draft.add_argument('--out', type=Path, required=True, help='new authored decision file; fill by, at and reason')
    placement_apply = commands.add_parser('reassign', parents=[after],
        help='apply or recover an authored placement; transfer slot acceptance, require canonical withdrawal first')
    placement_apply.add_argument('--file', type=Path, required=True, help='the exact studio-reassignment decision; retry the same file after interruption')
    reject_parser = commands.add_parser("reject", help="record that an iteration is not used, with the reason; a Production candidate's run records it as not selected", parents=[after])
    reject_parser.add_argument("--character", required=True)
    reject_parser.add_argument("--iteration", required=True)
    reject_parser.add_argument("--reason", required=True)
    reject_parser.add_argument("--actor", required=True, help="Actual person or agent making the non-selection decision")
    recipe_parser = commands.add_parser("recipe", help="read the saved request of the accepted image or an explicitly selected iteration", parents=[after])
    recipe_parser.add_argument("--character", required=True)
    recipe_parser.add_argument("--slot", required=True)
    recipe_parser.add_argument("--iteration", help="read this recorded iteration without accepting it")
    commands.add_parser("sync", help="check all historical sources and repair gallery, references and timelines", parents=[after])
    gallery_parser = commands.add_parser("gallery", help="write gallery.html and gallery.json: every image in order with prompt, model, settings, and seed", parents=[after])
    gallery_parser.add_argument("--out", type=Path, help="Where to write the HTML (default: <studio>/gallery.html); the JSON goes beside it")
    args = parser.parse_args(argv)
    import studio_workspace as implementation
    try:
        if args.command == "init":
            root = implementation.init(args.out, args.studio_id, args.title,
                        default_render_profile=args.default_render_profile,
                        default_creative_latitude=args.default_creative_latitude,
                        default_interaction_mode=args.default_interaction_mode,
                        default_style_family=args.default_style_family)
            print(implementation.status(root))
            return 0
        root = implementation.require_studio(args.studio or Path.cwd())
        if args.command == "status":
            print(implementation.status(root))
        elif args.command == "credentials":
            import service_auth
            if args.auth_command == "prepare":
                report = service_auth.prepare(root, args.service,
                    environment=args.environment, stored=args.stored)
            elif args.auth_command == "set":
                report = service_auth.set_from_input(root, args.service,
                    from_env=args.from_env, stdin=args.stdin)
            elif args.auth_command == "remove":
                report = service_auth.remove(root, args.service)
            else:
                report = service_auth.status(root, args.service)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 3
        elif args.command == "character":
            home = implementation.add_character(root, args.character, args.profile)
            print(f"added {args.character} at {home}")
        elif args.command == "iterate":
            row = implementation.iterate(root, args.character, args.slot, args.result, package=args.package, request=args.request,
                          response=args.response, note=args.note, package_companion=args.package_companion)
            print(json.dumps(row, ensure_ascii=False, indent=2))
        elif args.command == "attach-package":
            row = implementation.attach_package(root, args.character, args.iteration, package=args.package,
                package_companion=args.package_companion, evidence=args.evidence, actor=args.actor, reason=args.reason)
            print(json.dumps(row, ensure_ascii=False, indent=2))
        elif args.command == "accept":
            print(json.dumps(implementation.accept(root, args.character, args.iteration), ensure_ascii=False, indent=2))
        elif args.command == 'draft-reassignment':
            import studio_placement
            decision = studio_placement.draft(root, args.character, args.iteration, args.slot)
            implementation.execution_contract.atomic(args.out, implementation.execution_contract.encoded(decision))
            print(json.dumps({'ok': True, 'file': str(args.out), 'decision': decision}, ensure_ascii=False, indent=2))
        elif args.command == 'reassign':
            import studio_placement
            print(json.dumps(studio_placement.reassign(root, implementation.read_json(args.file)), ensure_ascii=False, indent=2))
        elif args.command == "reject":
            print(json.dumps(implementation.reject(root, args.character, args.iteration, args.reason, actor=args.actor), ensure_ascii=False, indent=2))
        elif args.command == "recipe":
            print(json.dumps(implementation.recipe(root, args.character, args.slot, iteration=args.iteration), ensure_ascii=False, indent=2))
        elif args.command == "sync":
            import studio_activity as activity
            report = activity.refresh(root)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 1
        elif args.command == "gallery":
            html_path, json_path = implementation.write_gallery(root, args.out)
            print(f"wrote {html_path} and {json_path}")
    except (ValueError, OSError) as exc:
        if args.command in {"credentials", 'draft-reassignment', 'reassign'}:
            from production_diagnostics import ProductionError, exit_code, from_exception
            phase = 'credential-management' if args.command == 'credentials' else 'placement'
            diagnostic = _operation_context.safe_value(from_exception(exc, phase=phase),
                secrets=_operation_context.current().secrets if _operation_context.current() else ())
            print(json.dumps({"ok": False, "diagnostics": [diagnostic]}, ensure_ascii=False, indent=2))
            print("error: " + diagnostic["message"], file=sys.stderr)
            return exit_code(diagnostic["code"]) if isinstance(exc, ProductionError) else 2
        print(f"error: {implementation._explain(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
