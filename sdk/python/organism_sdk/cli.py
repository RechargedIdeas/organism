"""Organism CLI — serve / status / validate-config / generative evolve (v1.9)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


def _add_config(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", "-c", default=None, help="Path to deploy YAML/JSON")


def _add_data_root(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--data-root",
        default=None,
        help="Organism data root (artifacts/organisms). Default: ./organism_data",
    )


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


def _data_root(args: argparse.Namespace) -> Path:
    if args.data_root:
        return Path(args.data_root)
    return Path.cwd() / "organism_data"


def _build_generative(args: argparse.Namespace) -> dict[str, Any]:
    from organism_sdk.deploy.config import default_cpu_only_config, load_deploy_config
    from organism_sdk.deploy.stack import build_minimal_stack
    from organism_sdk.generative import (
        ArtifactStore,
        AssetPipeline,
        CodePipeline,
        DraftReplayLog,
        EvolutionRuntime,
        OrganismStore,
        SkillRegistry,
        resolve_backend,
    )
    from organism_sdk.trace import V02TraceSink

    root = _data_root(args)
    art = ArtifactStore(root / "artifacts")
    replay = DraftReplayLog(root / "artifacts" / "draft_replay.json")
    backend_name = getattr(args, "backend", None)
    pipe = CodePipeline(art, backend=resolve_backend(backend_name), replay_log=replay)
    assets = AssetPipeline(art, assets_root=root / "assets")
    skills = SkillRegistry(art)
    organisms = OrganismStore(root / "organisms")
    organisms.ensure_default()
    cfg = load_deploy_config(args.config) if getattr(args, "config", None) else default_cpu_only_config()
    stack = build_minimal_stack(cfg)
    stack.trace.attach_v02_sink(V02TraceSink())
    runtime = EvolutionRuntime(
        registry=stack.registry,
        trace=stack.trace,
        modules=stack.modules,
        pulse_on_promote=False,
    )
    return {
        "root": root,
        "art": art,
        "pipe": pipe,
        "assets": assets,
        "skills": skills,
        "organisms": organisms,
        "stack": stack,
        "runtime": runtime,
        "replay": replay,
    }


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_evolve_skill(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    deps = tuple(args.depends_on or ())
    skill, bundle = g["skills"].generate_skill(
        args.name,
        intent=args.intent,
        code_pipeline=g["pipe"],
        depends_on=deps,
        backend_name=getattr(args, "backend", None),
        auto_promote=False,
    )
    org = g["organisms"].get_active()
    if org is not None:
        g["organisms"].sync_skills(org.organism_id, g["skills"].list_skills())
        g["organisms"].log(
            org.organism_id,
            "skill_generate",
            f"CLI generated skill {skill.name}",
            payload={"skill_id": skill.skill_id, "bundle_id": bundle.bundle_id},
        )
    _print(
        {
            "ok": bundle.stage.value != "REJECTED",
            "skill": skill.as_dict(),
            "bundle": bundle.as_dict(),
            "organism_id": org.organism_id if org else None,
        }
    )
    return 0


def _cmd_evolve_looks(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    if args.pack:
        result = g["assets"].evolve_pack(args.brief)
    else:
        result = g["assets"].evolve_looks(args.brief, kind=args.kind)  # type: ignore[arg-type]
    org = g["organisms"].get_active()
    if org is not None and (result.get("ok") if isinstance(result, dict) else True):
        g["organisms"].sync_appearance(org.organism_id, g["assets"].appearance)
        g["organisms"].log(
            org.organism_id,
            "looks_evolve",
            f"CLI looks evolve pack={bool(args.pack)}",
            payload={"brief": args.brief[:80], "pack": bool(args.pack)},
        )
    _print({"ok": True, "result": result, "organism_id": org.organism_id if org else None})
    return 0


def _cmd_evolve_code(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    bundle = g["pipe"].evolve(args.intent, auto_promote=bool(args.auto_promote))
    org = g["organisms"].get_active()
    if org is not None:
        g["organisms"].add_code_revision(org.organism_id, bundle.as_dict())
        g["organisms"].log(
            org.organism_id,
            "code_evolve",
            f"CLI code evolve {bundle.bundle_id}",
            payload={"bundle_id": bundle.bundle_id, "stage": bundle.stage.value},
        )
    hot = None
    if bundle.may_control:
        hot = g["runtime"].after_promote(bundle, organism_id=org.organism_id if org else "cli")
    _print(
        {
            "ok": True,
            "bundle": bundle.as_dict(),
            "hot_register": hot,
            "organism_id": org.organism_id if org else None,
            "product_limit": "promoted modules stay EXPLORATION / may_actuate=False",
        }
    )
    return 0


def _cmd_promote_skill(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    skill = g["skills"].promote_skill(args.skill_id, code_pipeline=g["pipe"])
    org = g["organisms"].get_active()
    hot = None
    bid = skill.code_bundle_id
    if bid:
        b = g["pipe"].bundles.get(bid)
        if b is not None and b.may_control:
            hot = g["runtime"].after_promote(
                b, skill=skill, organism_id=org.organism_id if org else "cli"
            )
    if org is not None:
        g["organisms"].sync_skills(org.organism_id, g["skills"].list_skills())
    _print({"ok": True, "skill": skill.as_dict(), "hot_register": hot})
    return 0


def _cmd_promote_code(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    bundle = g["pipe"].promote(args.bundle_id)
    org = g["organisms"].get_active()
    hot = g["runtime"].after_promote(bundle, organism_id=org.organism_id if org else "cli")
    _print(
        {
            "ok": True,
            "bundle": bundle.as_dict(),
            "hot_register": hot,
            "product_limit": (
                "hot-register caps at EXPLORATION; may_actuate=False forever "
                "unless separate audited actuation policy"
            ),
        }
    )
    return 0


def _cmd_rollback_code(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    rb = g["pipe"].rollback_last_promote(reason=args.reason)
    org = g["organisms"].get_active()
    result = g["runtime"].after_rollback(
        rb, organism_id=org.organism_id if org else "cli", reason=args.reason
    )
    _print({"ok": True, "bundle": rb.as_dict(), "after_rollback": result})
    return 0


def _cmd_bundle_export(args: argparse.Namespace) -> int:
    from organism_sdk.generative import export_organism_bundle

    g = _build_generative(args)
    org = g["organisms"].get_active()
    if org is None:
        org = g["organisms"].ensure_default()
    path = Path(args.path) if args.path else g["root"] / "bundles" / f"{org.organism_id}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    out = export_organism_bundle(
        profile=org,
        skills=g["skills"].list_skills(),
        appearance=g["assets"].appearance,
        asset_pipeline=g["assets"],
        dest=path,
    )
    _print({"ok": True, "result": out})
    return 0


def _cmd_bundle_import(args: argparse.Namespace) -> int:
    from organism_sdk.generative import import_organism_bundle

    g = _build_generative(args)
    path = Path(args.path)
    result = import_organism_bundle(
        path=path,
        organism_store=g["organisms"],
        skill_registry=g["skills"],
        asset_pipeline=g["assets"],
        switch_active=not args.no_activate,
    )
    _print({"ok": True, "result": result if isinstance(result, dict) else {"imported": True}})
    return 0


def _cmd_list_templates(args: argparse.Namespace) -> int:
    from organism_sdk.generative import list_templates

    _print({"ok": True, "templates": list_templates(), "backend_default": "template"})
    return 0


def _cmd_list_organisms(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    _print({"ok": True, "organisms": g["organisms"].list_summaries(), "active": g["organisms"].active_id()})
    return 0


def _cmd_replay_draft(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    entry = g["replay"].replay(args.entry_id)
    _print({"ok": True, "entry": entry.as_dict(), "source": entry.source})
    return 0


def _cmd_list_drafts(args: argparse.Namespace) -> int:
    g = _build_generative(args)
    _print({"ok": True, "entries": g["replay"].list_entries()})
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

    # --- Generative evolution (Desktop Evolution parity) ---
    p_es = sub.add_parser("evolve-skill", help="Evolve an Organism skill draft")
    _add_config(p_es)
    _add_data_root(p_es)
    p_es.add_argument("--name", required=True)
    p_es.add_argument("--intent", required=True)
    p_es.add_argument("--depends-on", nargs="*", default=[])
    p_es.add_argument("--backend", default=None, help="template|llm_stub|hosted_llm")
    p_es.set_defaults(func=_cmd_evolve_skill)

    p_el = sub.add_parser("evolve-looks", help="Evolve Organism looks (avatar/theme/pack)")
    _add_config(p_el)
    _add_data_root(p_el)
    p_el.add_argument("--brief", required=True)
    p_el.add_argument("--kind", default="avatar", choices=["avatar", "skin", "icon", "theme"])
    p_el.add_argument("--pack", action="store_true", help="Evolve multi-asset pack")
    p_el.set_defaults(func=_cmd_evolve_looks)

    p_ec = sub.add_parser("evolve-code", help="Evolve generative code bundle")
    _add_config(p_ec)
    _add_data_root(p_ec)
    p_ec.add_argument("--intent", required=True)
    p_ec.add_argument("--auto-promote", action="store_true")
    p_ec.add_argument("--backend", default=None)
    p_ec.set_defaults(func=_cmd_evolve_code)

    p_ps = sub.add_parser("promote-skill", help="Promote a skill through gates")
    _add_config(p_ps)
    _add_data_root(p_ps)
    p_ps.add_argument("--skill-id", required=True)
    p_ps.add_argument("--backend", default=None)
    p_ps.set_defaults(func=_cmd_promote_skill)

    p_pc = sub.add_parser("promote-code", help="Promote a code bundle through gates")
    _add_config(p_pc)
    _add_data_root(p_pc)
    p_pc.add_argument("--bundle-id", required=True)
    p_pc.add_argument("--backend", default=None)
    p_pc.set_defaults(func=_cmd_promote_code)

    p_rb = sub.add_parser("rollback-code", help="Rollback last code promote + deregister")
    _add_config(p_rb)
    _add_data_root(p_rb)
    p_rb.add_argument("--reason", default="cli_rollback")
    p_rb.add_argument("--backend", default=None)
    p_rb.set_defaults(func=_cmd_rollback_code)

    p_be = sub.add_parser("bundle-export", help="Export active Organism bundle zip")
    _add_config(p_be)
    _add_data_root(p_be)
    p_be.add_argument("--path", default=None)
    p_be.set_defaults(func=_cmd_bundle_export)

    p_bi = sub.add_parser("bundle-import", help="Import Organism bundle zip")
    _add_config(p_bi)
    _add_data_root(p_bi)
    p_bi.add_argument("--path", required=True)
    p_bi.add_argument("--no-activate", action="store_true")
    p_bi.set_defaults(func=_cmd_bundle_import)

    p_lt = sub.add_parser("list-templates", help="List generative template library")
    p_lt.set_defaults(func=_cmd_list_templates)

    p_lo = sub.add_parser("list-organisms", help="List Organism profiles")
    _add_config(p_lo)
    _add_data_root(p_lo)
    p_lo.set_defaults(func=_cmd_list_organisms)

    p_ld = sub.add_parser("list-drafts", help="List draft replay log entries")
    _add_config(p_ld)
    _add_data_root(p_ld)
    p_ld.set_defaults(func=_cmd_list_drafts)

    p_rd = sub.add_parser("replay-draft", help="Replay a draft by entry id")
    _add_config(p_rd)
    _add_data_root(p_rd)
    p_rd.add_argument("--entry-id", required=True)
    p_rd.set_defaults(func=_cmd_replay_draft)

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except Exception as e:
        _print({"ok": False, "error": f"{type(e).__name__}: {e}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
