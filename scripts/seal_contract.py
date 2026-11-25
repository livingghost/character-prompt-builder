#!/usr/bin/env python3
"""Seal the narrative contract's source record and its published files.

The contract publishes the hash of each file that answers it, and one of those
files carries the contract's digest, so the two feed each other. The cut is that
the digest is taken over the contract with the published block removed. That
fixes the order: settle the prose, write the digest into the reader that carries
it, then publish the hashes of the files as they now are. The last step moves a
reader's hash but not the digest, so a second run changes nothing.

The canonical knowledge record owns the published block. Add a file to that
section body, render documents with knowledge_document_build.py, run this command,
then run rebuild_metadata.py. Sealing leaves generated Markdown with its build
owner; it binds public contract files after that owner has generated them.

It also seals `protocols/contract-manifest.json`, the public contract set: the
byte hash of each listed schema, template and document, of the semantics
document and of the validator `scripts/protocol_contract.py`, then the digest
of the set. Which files are listed is read from the manifest. A file under
`protocols/` that the manifest does not list stops the seal and is named.

    python scripts/seal_contract.py            seal, and say what moved
    python scripts/seal_contract.py --check    say whether sealing would move anything, exit 1 if so
"""
from __future__ import annotations
import operation_context as _operation_context

import hashlib
import re
from pathlib import Path

import execution_contract as c
from knowledge_documents import decode_document, record_path
from knowledge_document_build import render_document


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "references/narrative-protocol"
CARRIER = "scripts/narrative.py"
PUBLISHED = re.compile(r"```text\n(?:scripts/\S+[ \t]+[0-9a-f]{64}\n)+```\n")
LINE = re.compile(r"^(scripts/\S+)[ \t]+[0-9a-f]{64}$", re.M)
DIGEST_FIELD = re.compile(r'(?m)^CONTRACT_SHA256 = "[0-9a-f]{64}"$')


def normalised(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sealed(document, carrier: str) -> tuple[bytes, str, str]:
    """Update the owning section body and carrier, preserving every other body."""
    bodies = [(section.section_id, section.raw.decode("utf-8")) for section in document.sections]
    blocks = [(identifier, match) for identifier, body in bodies for match in PUBLISHED.finditer(body)]
    if len(blocks) != 1:
        raise SystemExit(f"{record_path(CONTRACT)}: exactly one section must own the published block")
    owner, block = blocks[0]
    contract_text = render_document(document).decode("utf-8")
    digest = hashlib.sha256(PUBLISHED.sub("", contract_text).encode("utf-8")).hexdigest()
    if not DIGEST_FIELD.search(carrier):
        raise SystemExit(f"{CARRIER}: carries no CONTRACT_SHA256 field")
    carrier = DIGEST_FIELD.sub(f'CONTRACT_SHA256 = "{digest}"', carrier)
    hashes = {}
    for relative in LINE.findall(block.group(0)):
        if relative == CARRIER:
            hashes[relative] = hashlib.sha256(carrier.encode("utf-8")).hexdigest()
        elif (ROOT / relative).is_file():
            hashes[relative] = normalised(ROOT / relative)
        else:
            raise SystemExit(f"{relative}: published but not on disk")
    width = max(len(relative) for relative in hashes)
    rebuilt = "```text\n" + "".join(f"{relative:<{width}}  {digest}\n" for relative, digest in hashes.items()) + "```\n"
    source = {"sections": [{"id": identifier,
                            "body": body.replace(block.group(0), rebuilt) if identifier == owner else body}
                           for identifier, body in bodies]}
    return c.encoded(source), carrier, digest


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="Report what sealing would move; write nothing")
    args = parser.parse_args(argv)
    import protocol_contract as contract
    contract_path, carrier_path = ROOT / record_path(CONTRACT), ROOT / CARRIER
    contract_raw = contract_path.read_bytes()
    document = decode_document(CONTRACT, contract_raw)
    carrier = carrier_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    manifest_path = ROOT / contract.MANIFEST_PATH
    manifest = manifest_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        new_manifest = contract.seal_registry(manifest, ROOT)
    except ValueError as exc:
        raise SystemExit(f"{contract.MANIFEST_PATH}: {exc}")
    new_contract, new_carrier, digest = sealed(document, carrier)
    moved = [name for name, before, after in ((record_path(CONTRACT), contract_raw, new_contract), (CARRIER, carrier, new_carrier),
                                               (contract.MANIFEST_PATH, manifest, new_manifest))
             if before != after]
    print(f"CONTRACT_SHA256 = {digest}")
    rendered = render_document(decode_document(CONTRACT, new_contract)).decode("utf-8")
    for line in LINE.findall(PUBLISHED.search(rendered).group(0)):
        print(f"published {line}")
    if not moved:
        print("sealed: nothing moves")
        return 0
    if args.check:
        print("unsealed: sealing would rewrite " + ", ".join(moved))
        return 1
    c.atomic(contract_path, new_contract, replace=True)
    c.atomic(carrier_path, new_carrier.encode("utf-8"), replace=True)
    c.atomic(manifest_path, new_manifest.encode("utf-8"), replace=True)
    print("sealed: rewrote " + ", ".join(moved))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
