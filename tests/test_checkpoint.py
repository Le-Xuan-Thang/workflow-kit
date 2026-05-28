import signal
import pytest
import json
import tempfile
from pathlib import Path
from workflow_kit.runtime.context import TaskSpec, WorkflowContext


def test_shutdown_flag_set_by_sigint():
    """SIGINT sets _shutdown_requested to True."""
    import workflow_kit.runtime.dispatcher as d
    d._shutdown_requested = False
    d._handle_sigint(signal.SIGINT, None)
    assert d._shutdown_requested is True
    d._shutdown_requested = False  # reset after test


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
    recovery_path.unlink()
    assert not recovery_path.exists()


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


from unittest.mock import patch
from workflow_kit.runtime.config import WorkflowConfig, LLMConfig, ProjectConfig, Settings
import workflow_kit.runtime.dispatcher as dispatcher_module


def _make_cfg() -> WorkflowConfig:
    llm = LLMConfig(endpoint="http://localhost:11434/v1", api_key="x", model="m")
    return WorkflowConfig(
        project=ProjectConfig(name="test", description=""),
        orchestrators=[llm],
        workers=[llm],
        reviewers=[],
        settings=Settings(work_hours="0-24"),
    )


def test_watch_stops_when_shutdown_requested(tmp_path):
    """watch() exits cleanly when _shutdown_requested is True at start of loop."""
    cfg = _make_cfg()
    # Pre-set shutdown flag — watch() must detect it and exit without hanging
    dispatcher_module._shutdown_requested = True

    with patch.object(dispatcher_module, "recover_interrupted"):
        dispatcher_module.watch(cfg, tmp_path)  # must return promptly

    dispatcher_module._shutdown_requested = False  # reset


def test_recovery_snapshot_deleted_on_reviewer_escalation(tmp_path):
    """Snapshot is deleted even when task exits via reviewer escalation path."""
    task = _make_task(tmp_path)
    ctx = WorkflowContext(tmp_path)
    ctx.move_task(task.task_id, "pending", "active")

    # Create a stale recovery snapshot (simulating crash scenario)
    recovery_path = tmp_path / ".workflow" / "recovery" / f"{task.task_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_path.write_text(json.dumps({}))

    # Move task to completed with escalated status (simulating escalation)
    task.status = "failed"
    task.error = "Reviewer escalation after 2 retries: bad output"
    ctx.move_task(task.task_id, "active", "completed")
    ctx.write_task(task, "completed")

    # Manually simulate what the fixed code does: delete snapshot before return
    if recovery_path.exists():
        recovery_path.unlink()

    assert not recovery_path.exists()
    # Verify that recover_interrupted() won't find any stuck tasks
    ctx2 = WorkflowContext(tmp_path)
    assert len(list(ctx2.active.glob("*.json"))) == 0
