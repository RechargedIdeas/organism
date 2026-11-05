"""Organism CLI — serve / status / sandbox / validate-config / generative evolve (v1.10)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
    from organism_sdk.envstore import apply_to_environ

    apply_to_environ()
    cfg = load_deploy_config(args.config)
    issues = validate_deploy_config(cfg)
    if issues and not args.force:
        print(json.dumps({"ok": False, "issues": issues}, indent=2), file=sys.stderr)
        return 1

    from organism_sdk.work.store import default_store_path

    dry = bool(args.dry_run)
    port = args.port
    result = serve_stack(cfg, dry_run=dry, port=port, work_store=default_store_path())
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
    cfg = (
        load_deploy_config(args.config)
        if getattr(args, "config", None)
        else default_cpu_only_config()
    )
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
        result = g["assets"].evolve_looks(args.brief, kind=args.kind)
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
    _print(
        {
            "ok": True,
            "organisms": g["organisms"].list_summaries(),
            "active": g["organisms"].active_id(),
        }
    )
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


def _cmd_sandbox(args: argparse.Namespace) -> int:
    """organism sandbox status|run|self-check"""
    from organism_sdk.sandbox import OrganismSandbox, SandboxPolicy

    sb = OrganismSandbox()
    action = args.sandbox_action
    if action == "status":
        _print({"ok": True, **sb.status().as_dict()})
        return 0
    if action == "self-check":
        result = sb.self_check()
        _print(result.as_dict())
        return 0 if result.ok else 1
    if action == "run":
        argv = list(args.argv or [])
        if argv and argv[0] == "--":
            argv = argv[1:]
        if not argv:
            _print({"ok": False, "error": "sandbox run requires a command after --"})
            return 2
        policy = SandboxPolicy.from_env(label=args.label or "cli_run")
        if args.self_sandbox:
            policy = SandboxPolicy.self_containment()
        if args.timeout is not None:
            policy.timeout_s = float(args.timeout)
        if args.no_namespaces:
            policy.use_namespaces = False
        result = sb.run(argv, policy=policy)
        _print({"ok": result.ok, **result.as_dict()})
        return 0 if result.ok else 1
    _print({"ok": False, "error": f"unknown sandbox action: {action}"})
    return 2


def _cmd_work(args: argparse.Namespace) -> int:
    """organism work status|tickets|attention|pause|resume|stop|retry|evaluate|label|adopt|drive|runs|rerun"""
    from organism_sdk.work import operator
    from organism_sdk.work.store import WorkStore, default_store_path

    path = Path(args.store) if args.store else default_store_path()
    action = args.work_action
    if action == "drive":
        return _work_drive(args, path)
    reads_only = action in ("status", "tickets", "attention", "runs")
    if reads_only and not path.exists():
        _print({"ok": False, "error": f"no work store at {path}"})
        return 1
    stopped: str | None = None
    stopped_pid: int | None = None
    with WorkStore(path, read_only=reads_only) as store:
        if action == "status":
            _print(operator.status(store))
        elif action == "tickets":
            _print(operator.tickets(store))
        elif action == "attention":
            _print(operator.attention(store))
        elif action == "runs":
            try:
                _print(operator.runs(store, args.ticket))
            except KeyError:
                _print({"ok": False, "error": f"no ticket {args.ticket}"})
                return 1
        elif action == "rerun":
            try:
                assignment = operator.rerun(store, args.ticket)
            except KeyError:
                _print({"ok": False, "error": f"no open ticket {args.ticket}"})
                return 1
            except ValueError as error:
                _print({"ok": False, "error": str(error)})
                return 1
            _print({"ok": True, "ticket": args.ticket, "assignment": assignment})
        elif action in ("pause", "resume"):
            (operator.pause if action == "pause" else operator.resume)(store)
            _print({"ok": True, "paused": action == "pause"})
        elif action == "stop":
            try:
                stopped_pid = operator.stop(store, args.ticket)
            except KeyError:
                _print({"ok": False, "error": f"no open ticket {args.ticket}"})
                return 1
            stopped = args.ticket
        elif action == "retry":
            _print({"ok": True, "made_due": operator.retry(store, args.kind)})
        elif action == "label":
            from organism_sdk.work.domain import Verdict

            try:
                operator.label(store, args.decision, Verdict(args.verdict))
            except KeyError:
                _print({"ok": False, "error": f"no decision {args.decision}"})
                return 1
            _print({"ok": True, "decision": args.decision, "verdict": args.verdict})
        elif action == "adopt":
            from organism_sdk.signing import load_trust_store
            from organism_sdk.work import codec
            from organism_sdk.work.governance import PolicyRejected
            from organism_sdk.work.policy import Policy

            policy = codec.from_text(Policy, Path(args.policy_file).read_text(encoding="utf-8"))
            signature = bytes.fromhex(Path(args.signature).read_text(encoding="utf-8").strip())
            trust = load_trust_store(Path(args.trust))
            try:
                notified = operator.adopt(store, policy, signature=signature, trust=trust)
            except PolicyRejected as error:
                _print({"ok": False, "error": str(error)})
                return 1
            _print({"ok": True, "policy": policy.version, "notified": notified})
        else:
            try:
                report = operator.evaluate_triggers(store, row=args.row)
            except operator.NoActivePolicy as error:
                _print({"ok": False, "error": str(error)})
                return 1
            _print({"ok": True, "decided": report.decided, "unavailable": report.unavailable})
    if stopped is not None:
        # After the store is closed: ending a run's process group can take a few seconds.
        from organism_sdk.work.executors import end_process_group

        ended = stopped_pid is not None and end_process_group(stopped_pid)
        _print({"ok": True, "stopped": stopped, "process_ended": ended})
    return 0


def _work_drive(args: argparse.Namespace, path: Path) -> int:
    """Open Tickets for accepted Decisions and run them, through the executor file's settings."""
    from dataclasses import asdict

    from organism_sdk.deploy.config import load_deploy_config
    from organism_sdk.work import driver
    from organism_sdk.work.executors import executor_from_settings, load_executor
    from organism_sdk.work.store import WorkStore

    try:
        if args.executor:
            executor = load_executor(Path(args.executor))
        else:
            settings = load_deploy_config(args.config).work.executor
            if settings is None:
                raise ValueError(
                    "no executor is configured: pass --executor, or set work.executor in the "
                    "deploy config"
                )
            executor = executor_from_settings(settings)
    except (OSError, ValueError) as error:  # a DeployConfigError is a ValueError
        _print({"ok": False, "error": str(error)})
        return 1
    report = driver.drive(lambda: WorkStore(path), executor, limit=args.limit)
    if report.halted is not None:
        _print({"ok": False, "error": report.halted})
        return 1
    _print({"ok": True, **asdict(report)})
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
    p_serve.add_argument(
        "--port", type=int, default=None, help="Override health port (0=ephemeral)"
    )
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

    # --- Native sandbox (v1.10) ---
    p_sb = sub.add_parser("sandbox", help="Native Organism sandbox (status|run|self-check)")
    sb_sub = p_sb.add_subparsers(dest="sandbox_action", required=True)
    p_sbs = sb_sub.add_parser("status", help="Sandbox capabilities + policy")
    p_sbs.set_defaults(func=_cmd_sandbox)
    p_sbc = sb_sub.add_parser("self-check", help="Spawn/refuse/timeout self-check")
    p_sbc.set_defaults(func=_cmd_sandbox)
    p_sbr = sb_sub.add_parser("run", help="Run argv inside the native jail")
    p_sbr.add_argument("argv", nargs=argparse.REMAINDER, help="Command after -- ")
    p_sbr.add_argument("--label", default="cli_run")
    p_sbr.add_argument("--timeout", type=float, default=None)
    p_sbr.add_argument("--self-sandbox", action="store_true")
    p_sbr.add_argument("--no-namespaces", action="store_true")
    p_sbr.set_defaults(func=_cmd_sandbox)

    # --- Work agent (v1.12) ---
    store_option = argparse.ArgumentParser(add_help=False)
    store_option.add_argument(
        "--store",
        default=None,
        help="Work store file (default: $ORGANISM_WORK_STORE, else .organism/work/work.sqlite)",
    )
    p_work = sub.add_parser("work", help="Work agent: status, tickets, attention, pause, stop, ...")
    work_sub = p_work.add_subparsers(dest="work_action", required=True)
    for action, text in (
        ("status", "Counts and state, as JSON"),
        ("tickets", "Open Tickets, with their stages"),
        ("attention", "What needs a person"),
        ("pause", "Pause processing; intake keeps recording"),
        ("resume", "Resume processing"),
    ):
        work_sub.add_parser(action, parents=[store_option], help=text).set_defaults(func=_cmd_work)
    p_wstop = work_sub.add_parser(
        "stop", parents=[store_option], help="End a Ticket and drop its waiting replies"
    )
    p_wstop.add_argument("ticket")
    p_wstop.set_defaults(func=_cmd_work)
    p_wretry = work_sub.add_parser(
        "retry", parents=[store_option], help="Make waiting or failing effects due now"
    )
    p_wretry.add_argument("--kind", default=None)
    p_wretry.set_defaults(func=_cmd_work)
    p_weval = work_sub.add_parser(
        "evaluate", parents=[store_option], help="Decide undecided Triggers under the Policy"
    )
    p_weval.add_argument("--row", default="repo", help="The admission row the Triggers arrived in")
    p_weval.set_defaults(func=_cmd_work)
    p_wlabel = work_sub.add_parser(
        "label", parents=[store_option], help="Record a verdict on a Decision: agree or disagree"
    )
    p_wlabel.add_argument("decision")
    p_wlabel.add_argument("verdict", choices=["agree", "disagree"])
    p_wlabel.set_defaults(func=_cmd_work)
    p_wadopt = work_sub.add_parser(
        "adopt", parents=[store_option], help="Adopt a Policy that an approver has signed"
    )
    p_wadopt.add_argument("policy_file", help="The Policy, as JSON")
    p_wadopt.add_argument(
        "--signature", required=True, help="File with the approver's signature, hex"
    )
    p_wadopt.add_argument(
        "--trust", required=True, help="Trust store file: approver and author public keys, hex"
    )
    p_wadopt.set_defaults(func=_cmd_work)
    p_wdrive = work_sub.add_parser(
        "drive",
        parents=[store_option],
        help="Open Tickets for accepted Decisions and run them through the executor",
    )
    p_wdrive.add_argument(
        "--executor",
        default=None,
        help="Executor settings, as JSON: root, argv, prepare, slots. "
        "Default: work.executor in the deploy config",
    )
    p_wdrive.add_argument(
        "--config", "-c", default=None, help="Deploy config (default: $ORGANISM_CONFIG)"
    )
    p_wdrive.add_argument("--limit", type=int, default=10, help="Most Tickets to run in one pass")
    p_wdrive.set_defaults(func=_cmd_work)
    p_wruns = work_sub.add_parser(
        "runs", parents=[store_option], help="Each run of a Ticket, with the tail of its output"
    )
    p_wruns.add_argument("ticket")
    p_wruns.set_defaults(func=_cmd_work)
    p_wrerun = work_sub.add_parser(
        "rerun", parents=[store_option], help="Start again a Ticket that a restart interrupted"
    )
    p_wrerun.add_argument("ticket")
    p_wrerun.set_defaults(func=_cmd_work)

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except Exception as e:
        logger.warning("main failed", exc_info=True)
        _print({"ok": False, "error": f"{type(e).__name__}: {e}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
