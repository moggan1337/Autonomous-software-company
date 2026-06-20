#!/usr/bin/env python3
"""Entrypoint for the Autonomous Software Company.

Usage:
    python run.py serve [--host H] [--port P]   # start the dashboard + API (default)
    python run.py demo "your direction here"    # run one direction in the terminal
"""
from __future__ import annotations

import argparse
import sys


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("company.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from company.orchestrator import Company

    text = " ".join(args.directive) or "Launch a dark mode feature for our app."
    company = Company()
    mode = "Claude" if not company.settings.simulate else "simulation"
    print(f"\n=== Autonomous Software Company ({mode} mode) ===")
    print(f"Direction: {text}\n")

    company.submit_directive(text)
    company.run_until_idle()

    snap = company.snapshot()
    m = snap["metrics"]
    print("--- Activity feed ---")
    for e in reversed(snap["events"]):
        print(f"  [{e['department']:<11}] {e['message']}")
    print("\n--- Artifacts produced ---")
    for a in reversed(snap["artifacts"]):
        print(f"  ({a['department']}/{a['kind']}) {a['title']}")
    print(
        f"\n--- Summary ---\n  tasks={m['total_tasks']} done={m['done']} "
        f"blocked={m['blocked']} artifacts={m['artifacts']}\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous Software Company")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="Run the dashboard and API")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    p_demo = sub.add_parser("demo", help="Run a single direction in the terminal")
    p_demo.add_argument("directive", nargs="*")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args = parser.parse_args(["serve", *(argv or [])])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
