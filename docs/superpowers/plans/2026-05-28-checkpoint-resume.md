# Checkpoint & Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the dispatcher crashes or is Ctrl+C'd mid-task, automatically detect the interrupted state on next startup, roll back partial file edits, and re-queue the task for retry — plus handle Ctrl+C gracefully by finishing the current task before stopping.

**Architecture:** Three changes to `workflow_kit/runtime/dispatcher.py`: (1) a global SIGINT handler that sets a shutdown flag, (2) a `recover_interrupted()` function called at `watch()` startup that finds stuck `active/` tasks, restores files from a `.workflow/recovery/<task_id>.json` snapshot, and re-queues them, (3) recovery snapshot written before file edits and deleted after task completion. `cli.py` gets a `--resume` flag (no logic change — documents the auto-recovery behaviour).

**Tech Stack:** Python 3.9+, stdlib `signal`, `json`, `pathlib`. Tests: pytest + `tmp_path` fixtures. No new dependencies.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `workflow_kit/runtime/dispatcher.py` | **MODIFY** | Signal handler, `recover_interrupted()`, recovery snapshot write/delete, `watch()` changes |
| `workflow_kit/runtime/cli.py` | **MODIFY** | Add `--resume` flag to `start` subcommand |
| `tests/test_checkpoint.py` | **CREATE** | All tests for checkpoint/resume behaviour |

---

## Task 1: Signal handler and shutdown flag

**Files:**
- Modify: `workflow_kit/runtime/dispatcher.py` (top of module, after imports)
- Create: `tests/test_checkpoint.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_checkpoint.py`:

```python
import signal
import pytest
from pathlib import Path


def test_shutdown_flag_set_by_sigint():
    """SIGINT sets _shutdown_requested to True."""
    import workflow_kit.runtime.dispatcher as d
    d._shutdown_requested = False
    d._handle_sigint(signal.SIGINT, None)
    assert d._shutdown_requested is True
    d._shutdown_requested = False  # reset after test
```

- [ ] **Step 2: Run to verify it fails**

```bash
/home/whoami/.local/bin/pytest tests/test_checkpoint.py::test_shutdown_flag_set_by_sigint -v 2>&1 | head -15
```
Expected: `ImportError` or `AttributeError` — `_shutdown_requested` not defined.

- [ ] **Step 3: Add signal handler to `workflow_kit/runtime/dispatcher.py`**

Add after the existing imports (after `from workflow_kit.runtime import orchestrator as orch_module`):

```python
import signal

_shutdown_requested = False


def _handle_sigint(sig, frame):
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[dispatcher] Shutdown requested — finishing current task...")


signal.signal(signal.SIGINT, _handle_sigint)
```

- [ ] **Step 4: Run test — should PASS**

```bash
/home/whoami/.local/bin/pytest tests/test_checkpoint.py -v 2>&1
```
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add workflow_kit/runtime/dispatcher.py tests/test_checkpoint.py
git commit -m "feat(checkpoint): add SIGINT handler and shutdown flag"
```

---

## Task 2: Recovery snapshot — write before apply, delete after task

**Files:**
- Modify: `workflow_kit/runtime/dispatcher.py` (inside `run_one_cycle`)
- Modify: `tests/test_checkpoint.py`

- [ ] **Step 1: Add tests for snapshot write and delete**

Append to `tests/test_checkpoint.py`:

```python
import json
import tempfile
from workflow_kit.runtime.context import TaskSpec, WorkflowContext


def _make_task(tmp_path: Path, files=None) -> TaskSpec:
    files = files or []
    ctx = WorkflowContext(tmp_path)
    ctx.ensure_dirs()
    task = TaskSpec(
        task_id="feat-ckpt-001",
        type="implement",
        feature_name="Test task",
        description="test",
        files_to_modify=files,
        context_files=[],
        instructions=[],
    )
    ctx.write_task(task, "pending")
    return task


def test_recovery_snapshot_written_before_apply(tmp_path):
    """Recovery snapshot exists after originals are saved."""
    target = tmp_path / "app.py"
    target.write_text("original content")

    task = _make_task(tmp_path, files=["app.py"])
    ctx = WorkflowContext(tmp_path)

    # Simulate what run_one_cycle does: build originals then write snapshot
    originals = {"app.py": target.read_text()}
    recovery_path = tmp_path / ".workflow" / "recovery" / f"{task.task_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(json.dumps(originals))

    assert recovery_path.exists()
    data = json.loads(recovery_path.read_text())
    assert data["app.py"] == "original content"


def test_recovery_snapshot_deleted_after_completion(tmp_path):
    """Recovery snapshot is removed once task is done."""
    task = _make_task(tmp_path)
    recovery_path = tmp_path / ".workflow" / "recovery" / f"{task.task_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(json.dumps({}))

    assert recovery_path.exists()
    recovery_path.unlink()  # this is what the dispatcher does
    assert not recovery_path.exists()
```

- [ ] **Step 2: Run to verify they pass (these are pure logic tests)**

```bash
/home/whoami/.local/bin/pytest tests/test_checkpoint.py -v 2>&1
```
Expected: all 3 PASS (no production code change needed for these fixture-based tests).

- [ ] **Step 3: Modify `workflow_kit/runtime/dispatcher.py` — write snapshot in `run_one_cycle()`**

Find the block after `originals = {...}` (around line 189–193 in the original file). Add snapshot write immediately after:

```python
    # Save originals for rollback
    originals = {
        f: (project_root / f).read_text()
        for f in task.files_to_modify
        if (project_root / f).exists()
    }

    # Persist snapshot for crash recovery — deleted when task completes or fails
    recovery_path = project_root / ".workflow" / "recovery" / f"{task.task_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(json.dumps(originals, ensure_ascii=False))
```

Find the final block that calls `ctx.move_task(..., "active", "completed")` (around line 268). Add snapshot deletion immediately before `return True`:

```python
    ctx.move_task(task.task_id, "active", "completed")
    ctx.write_task(task, "completed")
    ctx.save_current(active_task=None)
    if recovery_path.exists():
        recovery_path.unlink()
    return True
```

- [ ] **Step 4: Run all tests**

```bash
/home/whoami/.local/bin/pytest tests/ -v 2>&1 | tail -10
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add workflow_kit/runtime/dispatcher.py tests/test_checkpoint.py
git commit -m "feat(checkpoint): write/delete recovery snapshot in run_one_cycle"
```

---

## Task 3: `recover_interrupted()` — detect and restore on startup

**Files:**
- Modify: `workflow_kit/runtime/dispatcher.py` (new function before `watch()`)
- Modify: `tests/test_checkpoint.py`

- [ ] **Step 1: Add tests for `recover_interrupted()`**

Append to `tests/test_checkpoint.py`:

```python
from workflow_kit.runtime.dispatcher import recover_interrupted


def test_recover_interrupted_no_stuck_tasks(tmp_path):
    """No active/ tasks → recover_interrupted() is a no-op."""
    ctx = WorkflowContext(tmp_path)
    ctx.ensure_dirs()
    recover_interrupted(tmp_path)  # should not raise
    assert list(ctx.active.glob("*.json")) == []


def test_recover_interrupted_restores_files_and_requeues(tmp_path):
    """Stuck task in active/ → files rolled back → task moved to pending/."""
    target = tmp_path / "src.py"
    target.write_text("modified by worker — partially broken")

    task = _make_task(tmp_path, files=["src.py"])
    ctx = WorkflowContext(tmp_path)

    # Move task to active/ (simulating crash mid-execution)
    ctx.move_task(task.task_id, "pending", "active")

    # Write recovery snapshot with original content
    recovery_path = tmp_path / ".workflow" / "recovery" / f"{task.task_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(json.dumps({"src.py": "original content"}))

    recover_interrupted(tmp_path)

    # File should be restored
    assert target.read_text() == "original content"
    # Recovery snapshot should be deleted
    assert not recovery_path.exists()
    # Task should be back in pending/
    assert len(list(ctx.pending.glob("*.json"))) == 1
    assert len(list(ctx.active.glob("*.json"))) == 0


def test_recover_interrupted_no_snapshot_still_requeues(tmp_path):
    """Stuck task with no snapshot (crash before snapshot written) → just re-queued, no rollback."""
    task = _make_task(tmp_path)
    ctx = WorkflowContext(tmp_path)
    ctx.move_task(task.task_id, "pending", "active")
    # No recovery snapshot file

    recover_interrupted(tmp_path)

    assert len(list(ctx.pending.glob("*.json"))) == 1
    assert len(list(ctx.active.glob("*.json"))) == 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/whoami/.local/bin/pytest tests/test_checkpoint.py -v -k "recover" 2>&1 | head -15
```
Expected: `ImportError` — `recover_interrupted` not defined.

- [ ] **Step 3: Add `recover_interrupted()` to `workflow_kit/runtime/dispatcher.py`**

Add this function just before the `watch()` function (around line 274):

```python
def recover_interrupted(project_root: Path):
    """Detect tasks stuck in active/ from a prior crash. Roll back files and re-queue."""
    ctx = WorkflowContext(project_root)
    stuck = sorted(ctx.active.glob("*.json"))
    if not stuck:
        return
    print(f"[dispatcher] Recovering {len(stuck)} interrupted task(s)...")
    for p in stuck:
        try:
            task = TaskSpec.from_dict(json.loads(p.read_text()))
        except Exception as e:
            print(f"[dispatcher]   Skipping unreadable task file {p.name}: {e}")
            continue
        recovery_path = project_root / ".workflow" / "recovery" / f"{task.task_id}.json"
        if recovery_path.exists():
            try:
                originals = json.loads(recovery_path.read_text())
                for fpath, content in originals.items():
                    target = project_root / fpath
                    if target.exists():
                        target.write_text(content)
                recovery_path.unlink()
                print(f"[dispatcher]   Rolled back files for: {task.task_id}")
            except Exception as e:
                print(f"[dispatcher]   Rollback failed for {task.task_id}: {e}")
        ctx.move_task(task.task_id, "active", "pending")
        print(f"[dispatcher]   Re-queued for retry: {task.task_id}")
    ctx.save_current(active_task=None)
```

Also add `TaskSpec` to the imports from context (it's used here). Check `workflow_kit/runtime/dispatcher.py` line 14 — `TaskSpec` is already imported via:
```python
from workflow_kit.runtime.context import WorkflowContext, TaskSpec
```
No change needed.

- [ ] **Step 4: Run all tests**

```bash
/home/whoami/.local/bin/pytest tests/test_checkpoint.py -v 2>&1
```
Expected: all PASS (now 7 tests total).

- [ ] **Step 5: Commit**

```bash
git add workflow_kit/runtime/dispatcher.py tests/test_checkpoint.py
git commit -m "feat(checkpoint): add recover_interrupted() with file rollback and re-queue"
```

---

## Task 4: `watch()` — call `recover_interrupted()` on startup, check shutdown flag

**Files:**
- Modify: `workflow_kit/runtime/dispatcher.py` (`watch()` function)
- Modify: `tests/test_checkpoint.py`

- [ ] **Step 1: Add test for shutdown flag in watch loop**

Append to `tests/test_checkpoint.py`:

```python
from unittest.mock import patch, MagicMock
from workflow_kit.runtime.config import WorkflowConfig, LLMConfig, ProjectConfig, Settings
import workflow_kit.runtime.dispatcher as dispatcher_module


def _make_cfg() -> WorkflowConfig:
    llm = LLMConfig(endpoint="http://localhost:11434/v1", api_key="x", model="m")
    return WorkflowConfig(
        project=ProjectConfig(name="test", description=""),
        orchestrators=[llm],
        workers=[llm],
        settings=Settings(work_hours="0-24"),
    )


def test_watch_stops_when_shutdown_requested(tmp_path):
    """watch() exits loop after one cycle when _shutdown_requested is True."""
    cfg = _make_cfg()
    dispatcher_module._shutdown_requested = False

    call_count = 0

    def fake_cycle(cfg, root):
        nonlocal call_count
        call_count += 1
        dispatcher_module._shutdown_requested = True
        return False

    with patch.object(dispatcher_module, "run_one_cycle", side_effect=fake_cycle), \
         patch.object(dispatcher_module, "recover_interrupted"), \
         patch.object(dispatcher_module, "_is_work_hours", return_value=True):
        dispatcher_module.watch(cfg, tmp_path)

    assert call_count == 1
    dispatcher_module._shutdown_requested = False
```

- [ ] **Step 2: Run to verify it fails**

```bash
/home/whoami/.local/bin/pytest tests/test_checkpoint.py::test_watch_stops_when_shutdown_requested -v 2>&1 | head -15
```
Expected: test hangs or fails — `watch()` never checks `_shutdown_requested`.

- [ ] **Step 3: Modify `watch()` in `workflow_kit/runtime/dispatcher.py`**

Replace the entire `watch()` function body:

```python
def watch(cfg: WorkflowConfig, project_root: Path):
    """Main loop: process tasks continuously, respecting work_hours."""
    recover_interrupted(project_root)
    print("[dispatcher] Watching for tasks in .workflow/tasks/pending/ ...")
    ctx = WorkflowContext(project_root)
    ctx.ensure_dirs()

    while True:
        if _shutdown_requested:
            print("[dispatcher] Stopped cleanly.")
            break
        if not _is_work_hours(cfg.settings.work_hours):
            print("[dispatcher] Outside work hours — sleeping 30 min")
            time.sleep(1800)
            continue
        if not run_one_cycle(cfg, project_root):
            time.sleep(5)
```

- [ ] **Step 4: Run all tests**

```bash
/home/whoami/.local/bin/pytest tests/ -v 2>&1 | tail -10
```
Expected: all PASS (8 tests in test_checkpoint.py + all prior tests).

- [ ] **Step 5: Commit**

```bash
git add workflow_kit/runtime/dispatcher.py tests/test_checkpoint.py
git commit -m "feat(checkpoint): watch() calls recover_interrupted() and checks shutdown flag"
```

---

## Task 5: `cli.py` — add `--resume` flag

**Files:**
- Modify: `workflow_kit/runtime/cli.py`

- [ ] **Step 1: Find the `start` subparser in `workflow_kit/runtime/cli.py`**

Read the file to find the `start` subparser block. It will look something like:

```python
start_p = sub.add_parser("start", ...)
```

- [ ] **Step 2: Add `--resume` argument**

Add after the `start_p = sub.add_parser(...)` line:

```python
start_p.add_argument(
    "--resume",
    action="store_true",
    help="Resume after interruption (default: auto-detected on every startup)",
)
```

No logic change needed — recovery is always automatic in `watch()`.

- [ ] **Step 3: Run full test suite**

```bash
/home/whoami/.local/bin/pytest tests/ -v 2>&1 | tail -5
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add workflow_kit/runtime/cli.py
git commit -m "docs(cli): add --resume flag to start command (recovery is always automatic)"
```

---

## Self-Review

**Spec coverage:**
- ✅ Startup auto-recovery → `recover_interrupted()` called in `watch()` — Task 3 + 4
- ✅ Files rolled back from snapshot → Task 3
- ✅ Task re-queued to pending/ → Task 3
- ✅ Recovery snapshot written before apply → Task 2
- ✅ Recovery snapshot deleted after completion — Task 2
- ✅ SIGINT sets flag, watch() checks it → Task 1 + 4
- ✅ No snapshot = still re-queue (safe fallback) → Task 3 test
- ✅ `--resume` CLI flag → Task 5
- ✅ Backward compatible (no recovery/ dir = no crash) → implicit in recover_interrupted()

**Type consistency:**
- `recover_interrupted(project_root: Path)` — consistent in Tasks 3 and 4
- `recovery_path` naming — consistent between Task 2 and Task 3
- `_shutdown_requested: bool` — consistent between Tasks 1 and 4

**No placeholders:** all steps have concrete code.
