---
name: workflow-monitor
description: Open the full live dashboard — either a Rich TUI in the terminal or the web dashboard at localhost:7860. Use when you want live task queue, log tail, and pause/resume controls.
---

# Workflow Monitor

Launch the live monitoring dashboard. Two modes — ask the user which they prefer if not specified.

## Modes

### TUI (default)
```bash
python -m workflow_kit monitor
```
Rich terminal dashboard with:
- Task queue panel (pending / active / completed)
- Live log tail
- Footer command bar: `/pause`, `/resume`, `/skip <id>`, `/retry <id>`, `/quit`

### Web dashboard
```bash
python -m workflow_kit dashboard
```
Opens FastAPI server on `dashboard_port` from `workflow.yaml` (default 7860).
Direct the user to: `http://localhost:<port>`

Features:
- Task cards with status, progress, timestamps
- Live log stream (SSE)
- Goals viewer
- Pause / Resume / Retry buttons

## Steps

### Step 1: Check dispatcher
Read `.workflow/dispatcher.pid`. If the dispatcher is not running, warn:
"Dispatcher is not running — monitor will show current state but no live updates. Start with /workflow-kit:workflow-start."

### Step 2: Ask mode (if not specified)
"Which monitoring mode? TUI (terminal) or Web (browser at localhost:PORT)?"

### Step 3: Launch

**TUI:** Run `python -m workflow_kit monitor` — this takes over the terminal until the user quits with `/quit` or Ctrl-C.

**Web:** Run `python -m workflow_kit dashboard` in the background, then tell the user: "Dashboard running at http://localhost:<port> — open in your browser."

## Codex / non-terminal note
In environments without a terminal (Codex App, sandboxed runners), TUI mode is not available. Default to Web mode or suggest `/workflow-kit:workflow-status` for a quick inline check.
