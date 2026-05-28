"""Cron-based overnight scheduling for workflow-kit."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

CRON_MARKER = "# workflow-kit"


def _parse_time(t: str) -> tuple[int, int]:
    """Parse 'HH:MM' into (hour, minute). Raises ValueError on bad format."""
    parts = t.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{t}'. Expected HH:MM")
    return int(parts[0]), int(parts[1])


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def _write_crontab(content: str) -> None:
    proc = subprocess.run(
        ["crontab", "-"],
        input=content,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr}")


def _build_cron_entries(
    start_h: int,
    start_m: int,
    stop_h: int,
    stop_m: int,
    project_root: Path,
    recurring: bool,
) -> tuple[str, str]:
    """Return (start_line, stop_line) for crontab."""
    python = "python -m workflow_kit.runtime.cli"
    log = project_root / ".workflow" / "logs" / "cron.log"
    start_sched = f"{start_m} {start_h} * * *"
    stop_sched = f"{stop_m} {stop_h} * * *"

    start_entry = (
        f"{start_sched} cd {project_root} && {python} start"
        f" >> {log} 2>&1 {CRON_MARKER}:start"
    )

    if recurring:
        stop_entry = (
            f"{stop_sched} cd {project_root} && {python} stop --report"
            f" >> {log} 2>&1 {CRON_MARKER}:stop"
        )
    else:
        # One-time: stop command self-removes cron entries after running
        stop_entry = (
            f"{stop_sched} cd {project_root} && {python} stop --report"
            f" && {python} schedule --remove"
            f" >> {log} 2>&1 {CRON_MARKER}:stop"
        )

    return start_entry, stop_entry


def install_schedule(
    start: str,
    stop: str,
    project_root: Path,
    recurring: bool = False,
) -> None:
    """Install cron entries for overnight scheduling.

    Replaces any existing workflow-kit cron entries.

    Args:
        start: Start time as 'HH:MM' (e.g. '21:00').
        stop: Stop time as 'HH:MM' (e.g. '09:00').
        project_root: Project root directory.
        recurring: If True, recur nightly. If False, run once then self-remove.

    Raises:
        ValueError: Bad time format.
        RuntimeError: crontab write failure.
    """
    start_h, start_m = _parse_time(start)
    stop_h, stop_m = _parse_time(stop)

    # Strip existing workflow-kit entries
    existing = _read_crontab()
    cleaned = "\n".join(
        line for line in existing.splitlines() if CRON_MARKER not in line
    )
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"

    start_line, stop_line = _build_cron_entries(
        start_h,
        start_m,
        stop_h,
        stop_m,
        project_root,
        recurring,
    )
    new_crontab = cleaned + start_line + "\n" + stop_line + "\n"
    _write_crontab(new_crontab)

    # Persist to .workflow/schedule.json
    sched_dir = project_root / ".workflow"
    sched_dir.mkdir(parents=True, exist_ok=True)
    (sched_dir / "schedule.json").write_text(
        json.dumps(
            {
                "start": start,
                "stop": stop,
                "recurring": recurring,
                "installed_at": datetime.now().isoformat(),
            },
            indent=2,
        )
    )


def remove_schedule(project_root: Path) -> None:
    """Remove all workflow-kit cron entries and schedule.json."""
    existing = _read_crontab()
    cleaned = "\n".join(
        line for line in existing.splitlines() if CRON_MARKER not in line
    )
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    _write_crontab(cleaned)

    sched_file = project_root / ".workflow" / "schedule.json"
    if sched_file.exists():
        sched_file.unlink()


def get_schedule(project_root: Path) -> dict | None:
    """Read current schedule from .workflow/schedule.json, or None if absent."""
    sched_file = project_root / ".workflow" / "schedule.json"
    if not sched_file.exists():
        return None
    try:
        return json.loads(sched_file.read_text())
    except json.JSONDecodeError:
        return None
