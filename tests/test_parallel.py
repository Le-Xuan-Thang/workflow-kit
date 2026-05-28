"""Tests for parallel task execution (Feature 3)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from workflow_kit.runtime.config import Settings, load_config
from workflow_kit.runtime.context import WorkflowContext, TaskSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_YAML = """
project:
  name: test-parallel
  description: test

orchestrator:
  endpoint: http://localhost:11434/v1/chat/completions
  api_key: ollama
  model: llama3.1:8b

worker:
  endpoint: http://localhost:11434/v1/chat/completions
  api_key: ollama
  model: llama3.1:8b
"""

YAML_WITH_MAX_PARALLEL = MINIMAL_YAML + """
settings:
  max_parallel_tasks: 4
"""


def _write_yaml(content: str) -> Path:
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "workflow.yaml").write_text(content)
    return Path(tmp)


def _make_task(task_id: str, files: list[str]) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        type="implement",
        feature_name=f"Feature {task_id}",
        description="test task",
        files_to_modify=files,
        context_files=[],
        instructions=["do something"],
    )


def _ctx_with_tasks(tasks: list[TaskSpec]) -> tuple[WorkflowContext, Path]:
    """Create a fresh WorkflowContext with given tasks in pending/."""
    tmp = Path(tempfile.mkdtemp())
    ctx = WorkflowContext(tmp)
    ctx.ensure_dirs()
    for task in tasks:
        ctx.write_task(task, "pending")
    return ctx, tmp


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


def test_max_parallel_tasks_in_settings_default_is_1():
    """Settings dataclass default must be 1 for backward compatibility."""
    s = Settings()
    assert s.max_parallel_tasks == 1


def test_load_config_max_parallel_tasks():
    """max_parallel_tasks is parsed from YAML settings section."""
    root = _write_yaml(YAML_WITH_MAX_PARALLEL)
    cfg = load_config(root)
    assert cfg.settings.max_parallel_tasks == 4


def test_load_config_max_parallel_tasks_defaults_to_1_when_absent():
    """When max_parallel_tasks is absent from YAML it defaults to 1."""
    root = _write_yaml(MINIMAL_YAML)
    cfg = load_config(root)
    assert cfg.settings.max_parallel_tasks == 1


# ---------------------------------------------------------------------------
# WorkflowContext thread-safety tests
# ---------------------------------------------------------------------------


def test_register_and_unregister_active_files():
    """register_active_files adds, unregister_active_files removes."""
    tmp = Path(tempfile.mkdtemp())
    ctx = WorkflowContext(tmp)

    ctx.register_active_files(["src/a.py", "src/b.py"])
    assert ctx.get_active_files() == {"src/a.py", "src/b.py"}

    ctx.unregister_active_files(["src/a.py"])
    assert ctx.get_active_files() == {"src/b.py"}

    ctx.unregister_active_files(["src/b.py"])
    assert ctx.get_active_files() == set()


def test_get_active_files_returns_copy():
    """get_active_files returns a snapshot, mutations don't affect internal state."""
    tmp = Path(tempfile.mkdtemp())
    ctx = WorkflowContext(tmp)
    ctx.register_active_files(["src/x.py"])

    snapshot = ctx.get_active_files()
    snapshot.add("src/injected.py")  # mutate the returned copy

    # Internal state must be unchanged
    assert ctx.get_active_files() == {"src/x.py"}


def test_get_next_pending_safe_excludes_conflicting_files():
    """get_next_pending_safe skips tasks whose files_to_modify overlap excluded_files."""
    task_a = _make_task("task-001", ["src/shared.py"])
    task_b = _make_task("task-002", ["src/other.py"])

    ctx, _ = _ctx_with_tasks([task_a, task_b])

    # Exclude the file that task_a touches — should return task_b
    result = ctx.get_next_pending_safe(excluded_files={"src/shared.py"})
    assert result is not None
    assert result.task_id == "task-002"


def test_get_next_pending_safe_returns_none_when_all_conflict():
    """Returns None when every pending task conflicts with excluded files."""
    task_a = _make_task("task-001", ["src/shared.py"])
    task_b = _make_task("task-002", ["src/shared.py"])

    ctx, _ = _ctx_with_tasks([task_a, task_b])

    result = ctx.get_next_pending_safe(excluded_files={"src/shared.py"})
    assert result is None


def test_get_next_pending_safe_returns_first_when_no_conflict():
    """Returns the first pending task when excluded_files is empty."""
    task_a = _make_task("task-001", ["src/a.py"])
    task_b = _make_task("task-002", ["src/b.py"])

    ctx, _ = _ctx_with_tasks([task_a, task_b])

    result = ctx.get_next_pending_safe(excluded_files=set())
    assert result is not None
    assert result.task_id == "task-001"


# ---------------------------------------------------------------------------
# Parallel dispatch logic tests
# ---------------------------------------------------------------------------


def test_parallel_tasks_no_file_conflict_both_run():
    """Two tasks with disjoint files_to_modify can both be dispatched."""
    task_a = _make_task("task-001", ["src/module_a.py"])
    task_b = _make_task("task-002", ["src/module_b.py"])

    ctx, _ = _ctx_with_tasks([task_a, task_b])

    # Simulate picking first task
    active_files: set[str] = set()
    first = ctx.get_next_pending_safe(active_files)
    assert first is not None
    active_files.update(first.files_to_modify)

    # Second task should still be available (no file conflict)
    second = ctx.get_next_pending_safe(active_files)
    assert second is not None
    assert second.task_id != first.task_id


def test_parallel_tasks_file_conflict_only_one_runs():
    """Two tasks sharing a file: second cannot be dispatched while first is active."""
    shared_file = "src/shared_module.py"
    task_a = _make_task("task-001", [shared_file])
    task_b = _make_task("task-002", [shared_file])

    ctx, _ = _ctx_with_tasks([task_a, task_b])

    # Pick first task and register its files as active
    active_files: set[str] = set()
    first = ctx.get_next_pending_safe(active_files)
    assert first is not None
    active_files.update(first.files_to_modify)

    # Second task shares a file — must NOT be dispatchable
    second = ctx.get_next_pending_safe(active_files)
    assert second is None


def test_parallel_tasks_second_runs_after_first_completes():
    """After first task's files are unregistered, second task becomes available."""
    shared_file = "src/shared_module.py"
    task_a = _make_task("task-001", [shared_file])
    task_b = _make_task("task-002", [shared_file])

    ctx, _ = _ctx_with_tasks([task_a, task_b])

    # Pick and "start" first task: move it to active and register its files
    first = ctx.get_next_pending_safe(set())
    assert first is not None
    ctx.move_task(first.task_id, "pending", "active")
    ctx.register_active_files(first.files_to_modify)

    # Second cannot run yet (file conflict)
    assert ctx.get_next_pending_safe(ctx.get_active_files()) is None

    # First completes — unregister its files (it's already moved out of pending)
    ctx.unregister_active_files(first.files_to_modify)

    # Now second task is available in pending
    result = ctx.get_next_pending_safe(ctx.get_active_files())
    assert result is not None
    assert result.task_id == "task-002"
