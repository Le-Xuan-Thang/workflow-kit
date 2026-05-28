import pytest
from workflow_kit.runtime.context import TaskSpec
from workflow_kit.runtime.reviewer import detect_domain, ReviewResult


def _make_task(**kwargs) -> TaskSpec:
    defaults = dict(
        task_id="feat-001",
        type="implement",
        feature_name="Add login",
        description="implement login feature",
        files_to_modify=["app.py"],
        context_files=[],
        instructions=["add login function"],
    )
    defaults.update(kwargs)
    return TaskSpec(**defaults)


def test_detect_domain_code_reviewer_default():
    task = _make_task(description="implement login function", type="implement")
    assert detect_domain(task) == "code-reviewer"


def test_detect_domain_editor_from_description():
    task = _make_task(description="write README documentation for the api", type="implement")
    assert detect_domain(task) == "editor"


def test_detect_domain_devops_from_type():
    task = _make_task(feature_name="Deploy to k8s", description="deploy container", type="implement")
    assert detect_domain(task) == "devops"


def test_detect_domain_data_scientist():
    task = _make_task(description="train ml model on dataset pipeline", type="implement")
    assert detect_domain(task) == "data-scientist"


def test_detect_domain_researcher():
    task = _make_task(description="literature survey on attention mechanisms", type="implement")
    assert detect_domain(task) == "researcher"


def test_review_result_fields():
    r = ReviewResult(passed=True, feedback="Looks good", domain="code-reviewer", model="claude-sonnet-4-6")
    assert r.passed is True
    assert r.feedback == "Looks good"
    assert r.domain == "code-reviewer"
    assert r.model == "claude-sonnet-4-6"


import tempfile
from pathlib import Path
from workflow_kit.runtime.reviewer import (
    DEFAULT_PROFILES,
    load_reviewer_profile,
    build_reviewer_prompt,
    parse_review_response,
)


def test_default_profiles_has_all_domains():
    for domain in ["code-reviewer", "editor", "researcher", "designer", "data-scientist", "devops"]:
        assert domain in DEFAULT_PROFILES
        assert len(DEFAULT_PROFILES[domain]) > 20


def test_load_reviewer_profile_returns_default_when_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        profile = load_reviewer_profile("code-reviewer", Path(tmp))
    assert "code" in profile.lower() or "review" in profile.lower()


def test_load_reviewer_profile_returns_custom_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        custom_dir = root / "workflow" / "reviewers"
        custom_dir.mkdir(parents=True)
        (custom_dir / "code-reviewer.md").write_text("Custom review instructions")
        profile = load_reviewer_profile("code-reviewer", root)
    assert profile == "Custom review instructions"


def test_build_reviewer_prompt_contains_task_and_output():
    task = _make_task(feature_name="Add auth", description="implement JWT auth")
    prompt = build_reviewer_prompt(task, "def login(): return token")
    assert "Add auth" in prompt
    assert "def login()" in prompt
    assert "PASS" in prompt
    assert "FAIL" in prompt


def test_parse_review_response_pass():
    passed, feedback = parse_review_response("PASS\nLooks good, clean implementation.")
    assert passed is True
    assert "Looks good" in feedback


def test_parse_review_response_fail():
    passed, feedback = parse_review_response("FAIL\nMissing error handling on line 5.")
    assert passed is False
    assert "Missing error handling" in feedback


def test_parse_review_response_malformed_treated_as_fail():
    passed, feedback = parse_review_response("I am not sure about this implementation...")
    assert passed is False
    assert len(feedback) > 0


from unittest.mock import patch
from workflow_kit.runtime.config import LLMConfig
from workflow_kit.runtime.reviewer import call_reviewer


def _make_cfg() -> LLMConfig:
    return LLMConfig(endpoint="http://localhost:11434/v1/chat/completions", api_key="test", model="test-model")


def test_call_reviewer_pass(tmp_path):
    task = _make_task()
    with patch("workflow_kit.runtime.reviewer.call_llm", return_value="PASS\nClean implementation."):
        result = call_reviewer(task, "def add(a, b): return a + b", _make_cfg(), tmp_path)
    assert result.passed is True
    assert result.domain == "code-reviewer"
    assert result.model == "test-model"
    assert "Clean" in result.feedback


def test_call_reviewer_fail(tmp_path):
    task = _make_task(description="implement login feature")
    with patch("workflow_kit.runtime.reviewer.call_llm", return_value="FAIL\nNo input validation."):
        result = call_reviewer(task, "def login(u, p): return True", _make_cfg(), tmp_path)
    assert result.passed is False
    assert "No input validation" in result.feedback


def test_call_reviewer_llm_failure_treated_as_pass(tmp_path):
    task = _make_task()
    with patch("workflow_kit.runtime.reviewer.call_llm", return_value=None):
        result = call_reviewer(task, "def foo(): pass", _make_cfg(), tmp_path)
    assert result.passed is True
    assert "unavailable" in result.feedback.lower()
