---
name: workflow-start
description: Start (or restart) the dispatcher background process. The dispatcher picks tasks from pending/, calls the worker LLM, applies edits, commits, and automatically queues the next task. Run after workflow-plan.
---

# Workflow Start

Launch the dispatcher loop as a background process. It runs continuously: picks a pending task → calls the worker → applies edits → verifies syntax → commits → plans next task → repeat.

## Steps

### Step 1: Verify prerequisites
- `workflow.yaml` exists — if not: "Run /workflow-kit:workflow-init first."
- `goals.md` exists — if not: "Run /workflow-kit:workflow-init first."
- `.workflow/tasks/pending/` has at least one task — if empty: "Run /workflow-kit:workflow-plan first to create tasks."

### Step 2: Check if already running
Read `.workflow/dispatcher.pid`. If it exists, check if the PID is alive:
```bash
kill -0 <pid> 2>/dev/null && echo running || echo dead
```
- If running: "Dispatcher already running (PID N). Use /workflow-kit:workflow-status to check progress."
- If dead (stale PID): remove the PID file and continue.

### Step 3: Start dispatcher
```bash
python -m workflow_kit start &
```

Write the PID to `.workflow/dispatcher.pid`.

### Step 4: Report
```
✓ Dispatcher started (PID N)

  Pending tasks: N
  Worker: <model from workflow.yaml>
  Work hours: <setting>

Monitor progress:
  /workflow-kit:workflow-status   — quick inline check
  /workflow-kit:workflow-monitor  — live TUI or web dashboard
  python -m workflow_kit stop     — stop the dispatcher
```

## Stop
If the user says "stop", "pause", or passes `--stop`:
```bash
python -m workflow_kit stop
```
This sends SIGTERM to the dispatcher PID and removes `.workflow/dispatcher.pid`.
