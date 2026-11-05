"""Sign a Policy offline, as its approver (v1.12 W9; OPEN_DECISIONS item 3). Design record:
docs/v1.12/APPROVER_SIGNING.md.

Run this on the approver's own machine, never on the agent's. The seed is the approver's private
key. It is written and read only outside the repository, and this script refuses a path inside it.

    python approve_policy.py keygen SEED_FILE                 write a new seed, print its public key
    python approve_policy.py public SEED_FILE                 print the public key of a seed
    python approve_policy.py sign POLICY_JSON SEED_FILE SIGNATURE_FILE
                                                              sign the Policy's version, print it
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from organism_sdk.signing import generate_seed, public_key_for, sign
from organism_sdk.work import codec
from organism_sdk.work.governance import policy_payload
from organism_sdk.work.policy import Policy

# docs/v1.12/approver/approve_policy.py -> the repository root
REPO = Path(__file__).resolve().parents[3]


def _outside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise SystemExit(f"refused: {path} is inside the repository; keep the seed outside it")
    return resolved


def _read_seed(path: Path) -> bytes:
    seed = bytes.fromhex(_outside_repo(path).read_text(encoding="utf-8").strip())
    if len(seed) != 32:
        raise SystemExit(f"refused: {path} does not hold a 32-byte seed")
    return seed


def keygen(seed_file: Path) -> int:
    target = _outside_repo(seed_file)
    if target.exists():
        raise SystemExit(f"refused: {seed_file} exists; a seed is never overwritten")
    seed = generate_seed()
    target.write_text(seed.hex() + "\n", encoding="utf-8")
    if os.name == "posix":
        target.chmod(0o600)
    print(public_key_for(seed).hex())
    return 0


def public(seed_file: Path) -> int:
    print(public_key_for(_read_seed(seed_file)).hex())
    return 0


def sign_policy(policy_file: Path, seed_file: Path, signature_file: Path) -> int:
    policy = codec.from_text(Policy, policy_file.read_text(encoding="utf-8"))
    signature = sign(_read_seed(seed_file), policy_payload(policy.version))
    signature_file.write_text(signature.hex() + "\n", encoding="utf-8")
    print(policy.version)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sign a Policy offline, as its approver.")
    sub = parser.add_subparsers(dest="action", required=True)
    keygen_parser = sub.add_parser("keygen", help="Write a new seed, print its public key")
    keygen_parser.add_argument("seed_file", type=Path)
    public_parser = sub.add_parser("public", help="Print the public key of a seed")
    public_parser.add_argument("seed_file", type=Path)
    sign_parser = sub.add_parser("sign", help="Sign a Policy's version, print the version")
    sign_parser.add_argument("policy_file", type=Path)
    sign_parser.add_argument("seed_file", type=Path)
    sign_parser.add_argument("signature_file", type=Path)
    args = parser.parse_args(argv)
    if args.action == "keygen":
        return keygen(args.seed_file)
    if args.action == "public":
        return public(args.seed_file)
    return sign_policy(args.policy_file, args.seed_file, args.signature_file)


if __name__ == "__main__":
    raise SystemExit(main())
