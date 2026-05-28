from unittest.mock import patch, MagicMock
from pathlib import Path
from workflow_kit.runtime.config import LLMConfig, WorkflowConfig, ProjectConfig, Settings
from workflow_kit.runtime.context import TaskSpec
from workflow_kit.runtime.dispatcher import _resolve_reviewer_cfg
from workflow_kit.runtime.reviewer import ReviewResult


def _make_cfg(reviewers=None) -> WorkflowConfig:
    llm = LLMConfig(endpoint="http://localhost:11434/v1/chat/completions", api_key="ollama", model="llama3.1:8b")
    return WorkflowConfig(
        project=ProjectConfig(name="test", description="test"),
        orchestrators=[llm],
        workers=[llm],
        reviewers=reviewers or [],
        settings=Settings(),
    )


def _make_task(**kwargs) -> TaskSpec:
    defaults = dict(
        task_id="feat-001", type="implement", feature_name="Test",
        description="implement feature", files_to_modify=[], context_files=[], instructions=[],
    )
    defaults.update(kwargs)
    return TaskSpec(**defaults)


def test_resolve_reviewer_cfg_no_config_returns_none():
    cfg = _make_cfg(reviewers=[])
    task = _make_task()
    assert _resolve_reviewer_cfg(task, cfg) is None


def test_resolve_reviewer_cfg_global_fallback():
    reviewer_llm = LLMConfig(endpoint="https://api.anthropic.com", api_key="sk-x", model="claude-sonnet-4-6")
    cfg = _make_cfg(reviewers=[reviewer_llm])
    task = _make_task()
    result = _resolve_reviewer_cfg(task, cfg)
    assert result.model == "claude-sonnet-4-6"


def test_resolve_reviewer_cfg_per_task_overrides_global():
    global_llm = LLMConfig(endpoint="https://api.anthropic.com", api_key="sk-x", model="claude-sonnet-4-6")
    cfg = _make_cfg(reviewers=[global_llm])
    task = _make_task(reviewer={
        "endpoint": "https://api.openai.com/v1",
        "api_key": "sk-openai",
        "model": "gpt-4o",
    })
    result = _resolve_reviewer_cfg(task, cfg)
    assert result.model == "gpt-4o"


import json
import tempfile
from unittest.mock import patch, call as mock_call


def test_reviewer_fail_then_pass_results_in_completed(tmp_path):
    """Reviewer FAIL on first attempt → worker retries → reviewer PASS → task completed."""
    # Set up minimal workflow context
    ctx_dir = tmp_path / ".workflow" / "tasks"
    for d in ["pending", "active", "completed"]:
        (ctx_dir / d).mkdir(parents=True)
    (tmp_path / ".workflow" / "memory").mkdir(parents=True)

    task = _make_task(task_id="feat-retry-test", files_to_modify=[])
    task_json = tmp_path / ".workflow" / "tasks" / "pending" / "feat-retry-test.json"
    task_json.write_text(json.dumps(task.__dict__ if hasattr(task, '__dict__') else {
        "task_id": task.task_id, "type": task.type, "feature_name": task.feature_name,
        "description": task.description, "files_to_modify": [], "context_files": [],
        "instructions": [], "status": "pending", "error": None, "result": None,
        "created_at": "2026-01-01T00:00:00+00:00", "reviewer": None,
    }))

    reviewer_llm = LLMConfig(endpoint="https://api.anthropic.com", api_key="sk-x", model="claude-sonnet-4-6")
    cfg = _make_cfg(reviewers=[reviewer_llm])
    cfg.settings.max_retries = 2
    cfg.settings.auto_commit = False
    cfg.settings.verify_syntax = False

    from workflow_kit.runtime.reviewer import ReviewResult
    fail_result = ReviewResult(passed=False, feedback="Missing validation", domain="code-reviewer", model="claude-sonnet-4-6")
    pass_result = ReviewResult(passed=True, feedback="Looks good", domain="code-reviewer", model="claude-sonnet-4-6")

    with patch("workflow_kit.runtime.dispatcher.call_llm_with_fallback", return_value="def foo(): pass"), \
         patch("workflow_kit.runtime.dispatcher.call_reviewer", side_effect=[fail_result, pass_result]), \
         patch("workflow_kit.runtime.dispatcher.orch_module.plan_next_tasks"):
        from workflow_kit.runtime.dispatcher import run_one_cycle
        result = run_one_cycle(cfg, tmp_path)

    assert result is True
    completed = list((ctx_dir / "completed").glob("*.json"))
    assert len(completed) == 1
    task_data = json.loads(completed[0].read_text())
    assert task_data["status"] == "completed", f"Expected completed, got: {task_data.get('status')} error: {task_data.get('error')}"
