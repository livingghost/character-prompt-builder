#!/usr/bin/env python3
"""Show the exact request a prepared run sends, and hold the transfer, journal and recovery steps execute uses.

Usage:
  python scripts/dispatch.py <generation-package.json> --studio DIR --character ID --slot SLOT
      [--preview-out FILE]
  python scripts/dispatch.py --upscale --model ID --source IMAGE --scale N --render-intent FILE
      --request-validation-file FILE [--settings-file FILE] [--guidance "..."]
      --studio DIR --character ID --slot SLOT [--preview-out FILE]

The studio is the production root, and every relative path is a /-separated
path below it. A Generation Package names the run it is bound to; an upscale
goes under the run prepared for the studio's open task. The preview refuses
what `production_workflow.py execute` refuses for that run: a changed source,
a package, upscale input or recording target that differs from the sealed one,
and a run that already owns an execution. Authorization, cost and credentials
are what execute settles; the preview shows the cost the authorization covers.

The preview prints the render contract, then the model, the service and its
endpoint, the output count, whether the negative prompt is sent and the cost,
and then the exact request, so the author approves the thing that would be sent
rather than a description of it. `--preview-out FILE` saves the request with
its trace and the validation report. Nothing is claimed, uploaded or sent;
`production_workflow.py execute` is the one send path.

The service record (endpoint, auth, operations) is the `service-profiles`
resource, and the model's identifier and request keys on that service are the
model record's offering. The record's `transport` names the module that knows the
rest of the service; scripts/transport_contract.py states what that module defines.

When execute sends, the functions here keep the request and the answer in a run
journal under the studio's runs/, save every returned image (decoded when the
answer carries it inline, downloaded over https from a declared host when it
names a URL), and build the Upscale Package of an enlarged image. A send that
ends without an answer is journaled as indeterminate, and nothing is sent again.
"""
from __future__ import annotations
import operation_context as _operation_context


from pathlib import Path


from pack_runtime_cli import add_pack_runtime_arguments


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog="A relative path is a /-separated path below the studio root; an absolute path is taken as given. "
        "production_workflow.py execute sends the request.",
    )
    parser.add_argument("package", nargs="?", help="A Generation Package bound to a prepared run; absent with --upscale")
    parser.add_argument("--studio", type=Path, required=True, help="A directory in the studio the run belongs to")
    parser.add_argument("--character", help="Check the optional Studio character already selected by the run")
    parser.add_argument("--slot", help="Check the optional Studio slot already selected by the run")
    parser.add_argument("--upscale", action="store_true", help="Preview the upscale prepared for the studio's open task")
    parser.add_argument("--model", help="With --upscale: the upscaler record")
    parser.add_argument("--source", help="With --upscale: the image to enlarge")
    parser.add_argument("--scale", type=float, help="With --upscale: the factor, one the record declares")
    parser.add_argument("--settings-file", help="With --upscale: UTF-8 JSON settings file, or - for stdin")
    parser.add_argument("--render-intent", help="With --upscale: explicit rendering intent JSON file, or - for stdin")
    parser.add_argument("--guidance", help="With --upscale: a guidance prompt, where the record accepts one")
    parser.add_argument("--request-validation-file",
                        help="With --upscale: explicit validation record and evidence, or - for stdin")
    parser.add_argument("--preview-out", help="New file for the sealed request, its trace and the validation report")
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    import dispatch_runtime as implementation
    if args.upscale:
        if not (args.model and args.source and args.scale and args.render_intent and args.request_validation_file):
            parser.error("--upscale needs --model, --source, --scale, --render-intent and --request-validation-file")
    elif args.package is None:
        parser.error("a Generation Package, or --upscale")
    runtime = implementation.resolve_pack_runtime(parser, args)
    implementation.configure_pack_runtime(runtime.settings)
    from production_binding import new_output, report_failure
    try:
        root = implementation.studio.require_studio(args.studio)
        if args.preview_out is not None:
            new_output(root, args.preview_out, option="--preview-out", root_option="--studio")
        return implementation.dispatch_upscale(args, root) if args.upscale else implementation.dispatch_generation(args, root)
    except (ValueError, OSError) as exc:
        return report_failure(exc, phase="preview")
    finally:
        implementation.configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
