"""Organism CLI — serve / status / validate-config (v1.4)."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence


def _add_config(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", "-c", default=None, help="Path to deploy YAML/JSON")


def _cmd_validate_config(args: argparse.Namespace) -> int:
    from organism_sdk.deploy.config import load_deploy_config, validate_deploy_config

    cfg = load_deploy_config(args.config)
    issues = validate_deploy_config(cfg)
    out = {"ok": not issues, "issues": issues, "config": cfg.as_dict()}
    print(json.dumps(out, indent=2))
    return 0 if not issues else 1


def _cmd_status(args: argparse.Namespace) -> int:
    from organism_sdk.deploy.config import load_deploy_config, validate_deploy_config
    from organism_sdk.deploy.stack import build_minimal_stack
    from organism_sdk.deploy.status_facts import enrich_cli_status

    cfg = load_deploy_config(args.config)
    issues = validate_deploy_config(cfg)
    if issues and not args.force:
        print(json.dumps({"ok": False, "issues": issues}, indent=2))
        return 1
    stack = build_minimal_stack(cfg)
    print(json.dumps(enrich_cli_status(stack), indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from organism_sdk.deploy.config import load_deploy_config, validate_deploy_config
    from organism_sdk.deploy.serve import serve_stack

    cfg = load_deploy_config(args.config)
    issues = validate_deploy_config(cfg)
    if issues and not args.force:
        print(json.dumps({"ok": False, "issues": issues}, indent=2), file=sys.stderr)
        return 1

    dry = bool(args.dry_run)
    port = args.port
    result = serve_stack(cfg, dry_run=dry, port=port)
    server = result.pop("_server", None)
    print(json.dumps({k: v for k, v in result.items()}, indent=2))
    if dry or args.once:
        if server is not None:
            server.shutdown()
        return 0
    if server is None:
        return 0
    try:
        import time

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="organism", description="Organism substrate CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate-config", help="Validate deploy profile")
    _add_config(p_val)
    p_val.set_defaults(func=_cmd_validate_config)

    p_stat = sub.add_parser("status", help="Build minimal stack and print status JSON")
    _add_config(p_stat)
    p_stat.add_argument("--force", action="store_true")
    p_stat.set_defaults(func=_cmd_status)

    p_serve = sub.add_parser("serve", help="Serve health/status HTTP for minimal stack")
    _add_config(p_serve)
    p_serve.add_argument("--dry-run", action="store_true", help="Build stack; do not bind")
    p_serve.add_argument("--once", action="store_true", help="Bind briefly then exit (tests)")
    p_serve.add_argument("--port", type=int, default=None, help="Override health port (0=ephemeral)")
    p_serve.add_argument("--force", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
