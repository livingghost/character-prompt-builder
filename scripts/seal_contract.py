#!/usr/bin/env python3
"""Seal the narrative contract against the files it publishes, in the order that stops.

The contract publishes the hash of each file that answers it, and one of those
files carries the contract's digest, so the two feed each other. The cut is that
the digest is taken over the contract with the published block removed. That
fixes the order: settle the prose, write the digest into the reader that carries
it, then publish the hashes of the files as they now are. The last step moves a
reader's hash but not the digest, so a second run changes nothing.

Which files are published is read from the block itself, so adding one is a
matter of adding its line to the block by hand and running this.

    python scripts/seal_contract.py            seal, and say what moved
    python scripts/seal_contract.py --check    say whether sealing would move anything, exit 1 if so
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "references/narrative-protocol.md"
CARRIER = "scripts/narrative.py"
PUBLISHED = re.compile(r"```text\n(?:scripts/\S+[ \t]+[0-9a-f]{64}\n)+```\n")
LINE = re.compile(r"^(scripts/\S+)[ \t]+[0-9a-f]{64}$", re.M)
DIGEST_FIELD = re.compile(r'(?m)^CONTRACT_SHA256 = "[0-9a-f]{64}"$')


def normalised(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sealed(contract: str, carrier: str) -> tuple[str, str, str]:
    """The contract and carrier as sealing leaves them, and the digest written."""
    block = PUBLISHED.search(contract)
    if not block:
        raise SystemExit(f"{CONTRACT}: the published block is not there")
    digest = hashlib.sha256(PUBLISHED.sub("", contract).encode("utf-8")).hexdigest()
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
    return contract.replace(block.group(0), rebuilt), carrier, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="Report what sealing would move; write nothing")
    args = parser.parse_args(argv)
    contract_path, carrier_path = ROOT / CONTRACT, ROOT / CARRIER
    contract = contract_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    carrier = carrier_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    new_contract, new_carrier, digest = sealed(contract, carrier)
    moved = [name for name, before, after in ((CONTRACT, contract, new_contract), (CARRIER, carrier, new_carrier))
             if before != after]
    print(f"CONTRACT_SHA256 = {digest}")
    for line in LINE.findall(PUBLISHED.search(new_contract).group(0)):
        print(f"published {line}")
    if not moved:
        print("sealed: nothing moves")
        return 0
    if args.check:
        print("unsealed: sealing would rewrite " + ", ".join(moved))
        return 1
    contract_path.write_bytes(new_contract.encode("utf-8"))
    carrier_path.write_bytes(new_carrier.encode("utf-8"))
    print("sealed: rewrote " + ", ".join(moved))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
