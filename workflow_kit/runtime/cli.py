"""CLI entry point: python -m workflow_kit [benchmark|plan|start|status|stop|schedule]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_benchmark(args, project_root: Path):
    from workflow_kit.runtime.config import load_config
    from workflow_kit.runtime.benchmarks import run_benchmark

    cfg = load_config(project_root)
    primary = cfg.workers[0]
    fallbacks = cfg.workers[1:]
    fb_note = f" (fallback: {', '.join(w.model for w in fallbacks)})" if fallbacks else ""
    print(f"Benchmarking worker: {primary.model}{fb_note} ...")
    profile = run_benchmark(primary, cfg.orchestrators, project_root)
    print(f"\nCapability profile for {profile['model']}:")
    for skill, score in profile["skills"].items():
        bar = "█" * int(score * 2) + "░" * (10 - int(score * 2))
        print(f"  {skill:<15} {bar}  {score}/5")
    print(f"\nOverall: {profile['overall']}/5")
    print(f"\nSummary: {profile['summary']}")


def cmd_plan(args, project_root: Path):
    from workflow_kit.runtime.config import load_config
    from workflow_kit.runtime.orchestrator import plan_next_tasks

    cfg = load_config(project_root)
    n = getattr(args, "n", 3)
    tasks = plan_next_tasks(cfg.orchestrators, project_root, n=n)
    print(f"\nPlanned {len(tasks)} task(s):")
    for t in tasks:
        print(f"  → {t.task_id}: {t.feature_name}")
    if tasks:
        print("\nReview in .workflow/tasks/pending/ then run: python -m workflow_kit start")


def cmd_start(args, project_root: Path):
    from workflow_kit.runtime.config import load_config
    from workflow_kit.runtime.dispatcher import watch

    cfg = load_config(project_root)
    watch(cfg, project_root)


def cmd_status(args, project_root: Path):
    from workflow_kit.runtime.config import load_config
    from workflow_kit.runtime.context import WorkflowContext

    try:
        from workflow_kit.runtime.schedule import get_schedule
    except ImportError:
        get_schedule = lambda _: None  # noqa: E731

    ctx = WorkflowContext(project_root)
    ctx.ensure_dirs()
    state = ctx.load_current()
    pending = ctx.pending_count()
    completed = list((project_root / ".workflow" / "tasks" / "completed").glob("*.json"))
    ok = sum(1 for f in completed if '"status": "completed"' in f.read_text())
    failed = len(completed) - ok
    decisions = ctx.completed_task_summaries(limit=3)

    print("\n── Workflow Status " + "─" * 40)
    print(f"  Active:    {state.get('active_task', 'none')}")
    print(f"  Pending:   {pending} task(s)")
    print(f"  Completed: {len(completed)} tasks ({ok} ok, {failed} failed)")

    # Show model chains from config (if available)
    try:
        cfg = load_config(project_root)
        worker_chain = " → ".join(w.model for w in cfg.workers)
        orch_chain = " → ".join(o.model for o in cfg.orchestrators)
        print(f"  Workers:   {worker_chain}")
        print(f"  Orch:      {orch_chain}")
    except Exception:
        pass

    cap = ctx.load_capability()
    if cap:
        print(f"  Benchmarked worker: {cap['model']} (overall {cap['overall']}/5)")
    sched = get_schedule(project_root)
    if sched:
        mode = "recurring" if sched.get("recurring") else "one-time"
        print(f"  Schedule:  {sched['start']} → {sched['stop']} ({mode})")
    if decisions:
        print("\n  Last completed:")
        for d in decisions:
            print(f"    {d}")
    print("─" * 58 + "\n")


def cmd_stop(args, project_root: Path):
    pid_file = project_root / ".workflow" / "dispatcher.pid"
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        import subprocess

        subprocess.run(["kill", pid], capture_output=True)
        pid_file.unlink(missing_ok=True)
        print(f"Stopped dispatcher (PID {pid})")
    else:
        print("No dispatcher PID file found — may not be running")

    if getattr(args, "report", False):
        try:
            from workflow_kit.runtime.reporter import generate_report, save_report
        except ImportError:
            print("reporter module not yet available — skipping report")
            return

        content = generate_report(project_root)
        path = save_report(project_root, content)
        print(f"\n📋 Morning report saved to: {path}")
        print("\n" + content)


def cmd_schedule(args, project_root: Path):
    try:
        from workflow_kit.runtime.schedule import install_schedule, remove_schedule, get_schedule
    except ImportError:
        print("schedule module not yet available — run Task 10 first")
        return

    if getattr(args, "remove", False):
        remove_schedule(project_root)
        print("✅ Schedule removed from crontab")
        return

    start = getattr(args, "start", None)
    stop = getattr(args, "stop", None)
    if not start or not stop:
        sched = get_schedule(project_root)
        if sched:
            mode = "recurring" if sched.get("recurring") else "one-time"
            print(f"Current schedule: {sched['start']} → {sched['stop']} ({mode})")
            print(f"Installed at: {sched.get('installed_at', 'unknown')}")
        else:
            print("No schedule configured.")
            print(
                "Usage: python -m workflow_kit schedule --start HH:MM --stop HH:MM [--recurring]"
            )
        return

    recurring = getattr(args, "recurring", False)
    install_schedule(start, stop, project_root, recurring=recurring)
    mode = "recurring nightly" if recurring else "one-time tonight"
    print(f"✅ Schedule installed ({mode}): start {start}, stop {stop}")
    print(f"   Agents will work from {start} → {stop}")
    if not recurring:
        print("   Cron entries auto-remove after stop fires.")
    print(f"   Morning report: .workflow/reports/")
    print(f"   Logs: .workflow/logs/cron.log")


def main():
    parser = argparse.ArgumentParser(prog="workflow_kit", description="workflow-kit CLI")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("benchmark", help="Run capability benchmark against worker model")
    plan_p = sub.add_parser("plan", help="Plan next tasks from goals.md")
    plan_p.add_argument("-n", type=int, default=3, help="Number of tasks to plan")
    sub.add_parser("start", help="Start dispatcher loop")
    sub.add_parser("status", help="Print current workflow status")
    stop_p = sub.add_parser("stop", help="Stop running dispatcher")
    stop_p.add_argument(
        "--report",
        action="store_true",
        help="Generate morning report after stopping",
    )
    sched_p = sub.add_parser("schedule", help="Set up overnight cron schedule")
    sched_p.add_argument("--start", metavar="HH:MM", help="Start time (e.g. 21:00)")
    sched_p.add_argument("--stop", metavar="HH:MM", help="Stop time (e.g. 09:00)")
    sched_p.add_argument(
        "--recurring",
        action="store_true",
        help="Recur every night (default: one-time)",
    )
    sched_p.add_argument(
        "--remove",
        action="store_true",
        help="Remove scheduled cron entries",
    )
    args = parser.parse_args()

    project_root = Path.cwd()

    dispatch = {
        "benchmark": cmd_benchmark,
        "plan": cmd_plan,
        "start": cmd_start,
        "status": cmd_status,
        "stop": cmd_stop,
        "schedule": cmd_schedule,
    }

    if args.command not in dispatch:
        parser.print_help()
        sys.exit(1)

    dispatch[args.command](args, project_root)


if __name__ == "__main__":
    main()
