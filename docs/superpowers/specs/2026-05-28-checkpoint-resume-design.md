# Checkpoint & Resume — Design Spec
_Date: 2026-05-28_

## Summary

When the dispatcher is interrupted mid-task (crash, power loss, Ctrl+C), the active task is left stuck in `.workflow/tasks/active/`. On next startup, the dispatcher detects this, restores file backups from a recovery snapshot, and moves the task back to `pending/` for retry. Ctrl+C triggers a graceful shutdown that finishes the current task before stopping.

---

## Architecture

### State layout (existing)

```
.workflow/
├── current.json          ← tracks active_task_id (already exists)
└── tasks/
    ├── pending/          ← tasks waiting to run
    ├── active/           ← task currently executing (stuck here on crash)
    └── completed/        ← done tasks
```

### New: recovery snapshots

```
.workflow/
└── recovery/
    └── <task_id>.json    ← {filepath: original_content} written before apply
                             deleted after task completes or rolls back
```

### Startup flow

```
watch() or run_one_cycle()
    │
    ├─► recover_interrupted(project_root)
    │       │
    │       ├─ .workflow/tasks/active/*.json exists?
    │       │       │
    │       │       └─► for each stuck task:
    │       │               load recovery/<task_id>.json
    │       │               restore original file contents
    │       │               delete recovery/<task_id>.json
    │       │               move task: active/ → pending/
    │       │               save_current(active_task=None)
    │       │
    │       └─ active/ empty → nothing to do
    │
    └─► normal dispatch loop
```

### Graceful Ctrl+C flow

```
SIGINT received
    │
    └─► _shutdown_requested = True
        print "[dispatcher] Shutdown requested — finishing current task..."

watch() loop — after each run_one_cycle() returns:
    └─► if _shutdown_requested: break
        print "[dispatcher] Stopped cleanly."

Result: current task always completes fully before stop.
        No partial state, no stuck active/ tasks.
```

---

## Implementation

### `runtime/dispatcher.py`

**Change 1 — Signal handler (top of module, after imports):**

```python
import signal

_shutdown_requested = False

def _handle_sigint(sig, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[dispatcher] Shutdown requested — finishing current task...")

signal.signal(signal.SIGINT, _handle_sigint)
```

**Change 2 — Recovery snapshot: written before apply, deleted on completion/rollback**

In `run_one_cycle()`, immediately after building `originals`:

```python
# Persist originals for crash recovery
recovery_path = project_root / ".workflow" / "recovery" / f"{task.task_id}.json"
recovery_path.parent.mkdir(parents=True, exist_ok=True)
recovery_path.write_text(json.dumps(originals, ensure_ascii=False))
```

After task completes or fails (before `return True`):

```python
# Clean up recovery snapshot
if recovery_path.exists():
    recovery_path.unlink()
```

**Change 3 — `recover_interrupted()` function:**

```python
def recover_interrupted(project_root: Path):
    """On startup, detect and recover any task stuck in active/ from a prior crash."""
    ctx = WorkflowContext(project_root)
    stuck = sorted(ctx.active.glob("*.json"))
    if not stuck:
        return
    print(f"[dispatcher] Recovering {len(stuck)} interrupted task(s)...")
    for p in stuck:
        task = TaskSpec.from_dict(json.loads(p.read_text()))
        recovery_path = project_root / ".workflow" / "recovery" / f"{task.task_id}.json"
        if recovery_path.exists():
            originals = json.loads(recovery_path.read_text())
            for fpath, content in originals.items():
                target = project_root / fpath
                if target.exists():
                    target.write_text(content)
            recovery_path.unlink()
            print(f"[dispatcher]   Rolled back files for: {task.task_id}")
        ctx.move_task(task.task_id, "active", "pending")
        print(f"[dispatcher]   Re-queued for retry: {task.task_id}")
    ctx.save_current(active_task=None)
```

**Change 4 — `watch()` calls `recover_interrupted()` on startup and checks shutdown flag:**

```python
def watch(cfg: WorkflowConfig, project_root: Path):
    recover_interrupted(project_root)       # ← new: always check on startup
    print("[dispatcher] Watching for tasks in .workflow/tasks/pending/ ...")
    ctx = WorkflowContext(project_root)
    ctx.ensure_dirs()

    while True:
        if _shutdown_requested:             # ← new: graceful stop
            print("[dispatcher] Stopped cleanly.")
            break
        if not _is_work_hours(cfg.settings.work_hours):
            print("[dispatcher] Outside work hours — sleeping 30 min")
            time.sleep(1800)
            continue
        if not run_one_cycle(cfg, project_root):
            time.sleep(5)
```

### `runtime/cli.py`

Add `--resume` flag to `start` subparser (documents that startup always auto-recovers):

```python
start_p.add_argument(
    "--resume",
    action="store_true",
    help="Resume after interruption (default: auto-detected on every startup)",
)
```

No logic change needed — recovery is always automatic.

---

## Files to Create / Modify

| File | Action | Change |
|---|---|---|
| `runtime/dispatcher.py` | **MODIFY** | Signal handler, `recover_interrupted()`, recovery snapshot write/delete, `watch()` changes |
| `runtime/context.py` | **no change** | `save_current` / `load_current` already sufficient |
| `runtime/cli.py` | **MODIFY** | Add `--resume` flag (documentation only) |

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| `recovery/<task_id>.json` missing on crash recovery | Skip rollback, still re-queue task to pending (safe — files may be unmodified) |
| Recovery JSON has invalid content | Log warning, skip rollback, re-queue |
| `active/` has multiple stuck tasks (e.g. previous run also crashed) | Recover all of them in order |
| Ctrl+C during sleep (not mid-task) | `_shutdown_requested = True`, loop breaks immediately on next iteration |
| Second Ctrl+C during task execution | User can force-kill with second Ctrl+C — Python default SIGINT re-raised after first is handled |

---

## Non-Goals

- No partial-progress resumption within a task (task always retries from scratch)
- No recovery for the orchestrator/planning phase (only dispatcher tasks)
- No distributed/multi-process lock file (single dispatcher process assumed)
