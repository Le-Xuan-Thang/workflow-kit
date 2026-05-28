---
name: workflow-status
description: Quick inline status check — shows active task, queue depth, completed count, and recent decisions. No TUI or browser needed. Use anytime to see what the dispatcher is doing.
---

# Workflow Status

Print a compact status snapshot directly in the conversation. No external tool is launched.

## Steps

### Step 1: Read state
```bash
python -m workflow_kit status
```

Reads `.workflow/current.json`, counts files in `pending/` / `active/` / `completed/`, and reads the last 3 lines of `.workflow/memory/decisions.md`.

### Step 2: Print inline

```
── Workflow Status ─────────────────────────────────
  Dispatcher: running (PID 12345)   ← or: stopped
  Active:     feat-003-dark-mode (started 4 min ago)
  Pending:    2 tasks
  Completed:  7 tasks (6 ✓  1 ✗)
  Progress:   58%

  Recent decisions:
  • [14:22] Built CSV export via llama3.1:70b
  • [13:55] Built confidence slider
  • [13:30] Built undo/redo keyboard shortcuts
─────────────────────────────────────────────────────
```

If no `.workflow/` directory exists: "workflow-kit not initialized in this project. Run /workflow-kit:workflow-init first."

If dispatcher is stopped and there are pending tasks: append "Run /workflow-kit:workflow-start to resume."
