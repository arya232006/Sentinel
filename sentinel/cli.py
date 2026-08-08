"""Sentinel command line.

    sentinel ci   --baseline report.json     regression gate; exits non-zero
    sentinel diff --baseline report.json     differential audit across models
    sentinel kb   [--list|--export]          inspect the learned technique KB

`ci` is the one that has to behave like a real build tool: exit codes are the
contract, and the human-readable output goes to stdout so it lands in a CI log.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

from sentinel import ci as ci_mod
from sentinel import config, differential
from sentinel.store import repo


def _default_authorizer() -> str:
    try:
        return f"sentinel-ci:{getpass.getuser()}"
    except Exception:
        return "sentinel-ci"


def _add_baseline_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--baseline", required=True, help="path to a Sentinel report JSON")
    p.add_argument(
        "--endpoint",
        default=None,
        help="target endpoint; defaults to the one recorded in the baseline",
    )
    p.add_argument("--target-id", default=None, help="override the baseline target id")
    p.add_argument(
        "--reruns",
        type=int,
        default=None,
        help=f"replays per finding (default {config.VERIFY_RERUNS})",
    )
    p.add_argument("--max-usd", type=float, default=None, help="hard budget cap")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a table")


def cmd_ci(args: argparse.Namespace) -> int:
    try:
        suffix = args.system_suffix or ""
        if args.patch_file:
            suffix = open(args.patch_file, encoding="utf-8").read()
        baseline = ci_mod.load_baseline(args.baseline)
        result = ci_mod.run_gate(
            baseline,
            endpoint=args.endpoint,
            target_id=args.target_id,
            reruns=args.reruns,
            authorizer=args.authorizer or _default_authorizer(),
            max_usd=args.max_usd,
            system_suffix=suffix,
        )
    except OSError as exc:
        print(f"\n  sentinel ci - GATE ERROR: {exc}\n", file=sys.stderr)
        return ci_mod.EXIT_ERROR
    except ci_mod.BaselineError as exc:
        # Cannot evaluate is not the same as passing.
        if args.json:
            print(json.dumps({"exit_code": ci_mod.EXIT_ERROR, "error": str(exc)}))
        else:
            print(f"\n  sentinel ci - GATE ERROR: {exc}\n", file=sys.stderr)
        return ci_mod.EXIT_ERROR

    print(json.dumps(result.to_dict(), indent=2, default=str) if args.json
          else ci_mod.format_report(result))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2, default=str)
    return result.exit_code


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        baseline = ci_mod.load_baseline(args.baseline)
        result = differential.run_differential(
            baseline,
            models=args.models,
            endpoint=args.endpoint,
            target_id=args.target_id,
            reruns=args.reruns,
            max_usd=args.max_usd,
        )
    except (ci_mod.BaselineError, ValueError) as exc:
        print(f"\n  sentinel diff - ERROR: {exc}\n", file=sys.stderr)
        return ci_mod.EXIT_ERROR

    print(json.dumps(result.to_dict(), indent=2, default=str) if args.json
          else differential.format_report(result))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, indent=2, default=str)
    return ci_mod.EXIT_OK


def cmd_kb(args: argparse.Namespace) -> int:
    repo.connect()
    rows: list[dict[str, Any]] = repo.list_learned_techniques(
        provenance=args.provenance, category=args.category
    )
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0

    from sentinel.knowledge.retrieval import load_techniques

    print()
    print(f"  curated techniques : {len(load_techniques())}")
    print(f"  learned techniques : {len(rows)}")
    print()
    if not rows:
        print("  (nothing learned yet - run an audit that confirms a finding)")
        print()
        return 0
    for t in rows:
        print(f"  {t['id']}")
        print(f"    category   : {t['category']}")
        print(f"    name       : {t['name']}")
        print(f"    exploits   : {t['exploits']}")
        print(f"    mechanism  : {t['mechanism']}")
        print(f"    signals    : {', '.join(t['signals_of_susceptibility']) or '-'}")
        print(
            f"    discovered : run {t['source_run_id']} against "
            f"{t['source_target']} [{t['provenance']}]"
        )
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentinel", description="Agentic AI red-team auditor"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ci = sub.add_parser(
        "ci",
        help="replay previously-confirmed findings; exit 1 if any reproduce",
        description=(
            "Regression gate. Replays only the confirmed findings in a baseline "
            "report against the target as it exists now. Exit 0 = all held, "
            "1 = a finding reopened, 2 = the gate could not be evaluated."
        ),
    )
    _add_baseline_args(p_ci)
    p_ci.add_argument(
        "--authorizer",
        default=None,
        help="recorded on the scope the gate mints for itself",
    )
    p_ci.add_argument("--output", default=None, help="also write the result as JSON")
    p_ci.add_argument(
        "--system-suffix",
        default=None,
        help="append this text to the target's system prompt for the gate - "
        "turns the gate into a pre-merge check on a proposed prompt change",
    )
    p_ci.add_argument(
        "--patch-file", default=None, help="read --system-suffix from a file"
    )
    p_ci.set_defaults(func=cmd_ci)

    p_diff = sub.add_parser(
        "diff",
        help="replay confirmed findings against several models",
        description=(
            "Differential audit. Replays each confirmed finding against the same "
            "target harness backed by each model in turn, to show whether a "
            "weakness is in the prompt or in the model."
        ),
    )
    _add_baseline_args(p_diff)
    p_diff.add_argument(
        "--models",
        nargs="+",
        default=None,
        help=f"models to compare (default: {' '.join(config.DIFFERENTIAL_MODELS)})",
    )
    p_diff.add_argument("--output", default=None, help="also write the result as JSON")
    p_diff.set_defaults(func=cmd_diff)

    p_kb = sub.add_parser(
        "kb", help="inspect techniques Sentinel discovered for itself"
    )
    p_kb.add_argument("--category", default=None)
    p_kb.add_argument(
        "--provenance",
        default=None,
        help="filter by live/shakedown/offline (default: all)",
    )
    p_kb.add_argument("--json", action="store_true")
    p_kb.set_defaults(func=cmd_kb)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
