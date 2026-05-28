# Cross-Provider Reviewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mandatory reviewer agent step after each worker output, using a separate LLM endpoint to eliminate sycophancy bias — reviewer issues PASS/FAIL + feedback, worker retries on FAIL.

**Architecture:** New `runtime/reviewer.py` module with domain detection, profile loading, and LLM call. `dispatcher.py` calls reviewer after syntax check passes; FAIL injects feedback into the existing retry loop. Config adds optional `reviewers:` list to `workflow.yaml`; no reviewer config = backward compatible skip.

**Tech Stack:** Python 3.9+, stdlib only (urllib, dataclasses, re) — same as existing runtime. Tests: pytest + unittest.mock.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `runtime/reviewer.py` | **CREATE** | `ReviewResult`, `detect_domain`, `DEFAULT_PROFILES`, `load_reviewer_profile`, `build_reviewer_prompt`, `parse_review_response`, `call_reviewer` |
| `runtime/config.py` | **MODIFY** | Add `reviewers: list[LLMConfig]` to `WorkflowConfig`; parse optional `reviewers` key |
| `runtime/context.py` | **MODIFY** | Add `reviewer: Optional[dict] = None` to `TaskSpec` |
| `runtime/dispatcher.py` | **MODIFY** | Add `_resolve_reviewer_cfg()`; insert reviewer gate in `run_one_cycle()` |
| `skills/init/SKILL.md` | **MODIFY** | Add Phase 7b: reviewer LLM setup |
| `skills/execute/SKILL.md` | **MODIFY** | Mention reviewer step and escalation |
| `README.md` | **MODIFY** | Document `reviewers:` section in workflow.yaml reference |
| `tests/__init__.py` | **CREATE** | Empty — marks tests as package |
| `tests/test_reviewer.py` | **CREATE** | All tests for reviewer.py |
| `tests/test_config_reviewer.py` | **CREATE** | Tests for config.py reviewer parsing |
| `tests/test_dispatcher_reviewer.py` | **CREATE** | Tests for dispatcher reviewer gate |

---

## Task 1: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/__init__.py`**

```python
```
(empty file)

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import sys
from pathlib import Path

# Ensure the package root is importable as workflow_kit
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 3: Verify import works**

```bash
cd /run/media/whoami/Data/Thang/MurineCyto-Det/workflow-kit
python -c "from workflow_kit.runtime.config import WorkflowConfig; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Install pytest if needed**

```bash
pip install pytest --quiet
pytest --version
```

Expected: `pytest X.Y.Z`

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: add test infrastructure"
```

---

## Task 2: `runtime/reviewer.py` — core data structures and domain detection

**Files:**
- Create: `runtime/reviewer.py`
- Create: `tests/test_reviewer.py`

- [ ] **Step 1: Write failing tests for `detect_domain` and `ReviewResult`**

Create `tests/test_reviewer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /run/media/whoami/Data/Thang/MurineCyto-Det/workflow-kit
pytest tests/test_reviewer.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'workflow_kit.runtime.reviewer'`

- [ ] **Step 3: Create `runtime/reviewer.py` — data structures + detect_domain**

```python
"""Reviewer agent: domain detection, profile loading, LLM call, PASS/FAIL parsing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from workflow_kit.runtime.config import LLMConfig
from workflow_kit.runtime.context import TaskSpec
from workflow_kit.runtime.worker import call_llm


@dataclass
class ReviewResult:
    passed: bool
    feedback: str
    domain: str
    model: str


DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "code-reviewer":  ["code", "feature", "bugfix", "refactor", "function", "class", "api", "implement"],
    "editor":         ["doc", "readme", "article", "write", "text", "markdown", "comment"],
    "researcher":     ["research", "analysis", "literature", "survey", "study", "paper"],
    "designer":       ["ui", "schema", "architecture", "design", "layout", "interface"],
    "data-scientist": ["data", "ml", "model", "pipeline", "dataset", "train"],
    "devops":         ["deploy", "infra", "ci", "docker", "k8s", "cloud"],
}


def detect_domain(task: TaskSpec) -> str:
    """Score each domain by keyword hits in task text; return highest-scoring domain."""
    text = f"{task.type} {task.feature_name} {task.description}".lower()
    scores = {
        domain: sum(1 for kw in keywords if kw in text)
        for domain, keywords in DOMAIN_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "code-reviewer"
```

- [ ] **Step 4: Run tests — domain detection + ReviewResult should pass**

```bash
pytest tests/test_reviewer.py -v 2>&1
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runtime/reviewer.py tests/test_reviewer.py
git commit -m "feat: add ReviewResult and detect_domain to reviewer.py"
```

---

## Task 3: `runtime/reviewer.py` — profile loading + prompt + response parsing

**Files:**
- Modify: `runtime/reviewer.py`
- Modify: `tests/test_reviewer.py`

- [ ] **Step 1: Add tests for profile loading, prompt building, response parsing**

Append to `tests/test_reviewer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reviewer.py -v -k "profile or prompt or parse or default" 2>&1
```

Expected: `ImportError` on `DEFAULT_PROFILES`, `load_reviewer_profile`, etc.

- [ ] **Step 3: Add DEFAULT_PROFILES, load_reviewer_profile, build_reviewer_prompt, parse_review_response to `runtime/reviewer.py`**

Append to `runtime/reviewer.py` (after `detect_domain`):

```python
DEFAULT_PROFILES: dict[str, str] = {
    "code-reviewer": (
        "You are a senior code reviewer. Evaluate the implementation for: "
        "correctness, edge cases, security, clarity, and adherence to the task spec. "
        "Respond with PASS or FAIL on the first line, followed by specific feedback."
    ),
    "editor": (
        "You are a technical editor. Evaluate the writing for: "
        "clarity, accuracy, completeness, and appropriate tone. "
        "Respond with PASS or FAIL on the first line, followed by specific feedback."
    ),
    "researcher": (
        "You are a research reviewer. Evaluate for: "
        "methodological soundness, citation quality, logical consistency, and completeness. "
        "Respond with PASS or FAIL on the first line, followed by specific feedback."
    ),
    "designer": (
        "You are a system designer. Evaluate for: "
        "architectural soundness, scalability, interface clarity, and alignment with requirements. "
        "Respond with PASS or FAIL on the first line, followed by specific feedback."
    ),
    "data-scientist": (
        "You are a data science reviewer. Evaluate for: "
        "statistical validity, data leakage risks, pipeline correctness, and reproducibility. "
        "Respond with PASS or FAIL on the first line, followed by specific feedback."
    ),
    "devops": (
        "You are a DevOps reviewer. Evaluate for: "
        "security, idempotency, rollback safety, resource efficiency, and operational clarity. "
        "Respond with PASS or FAIL on the first line, followed by specific feedback."
    ),
}


def load_reviewer_profile(domain: str, project_root: Path) -> str:
    """Load custom profile from workflow/reviewers/<domain>.md, fallback to DEFAULT_PROFILES."""
    custom = project_root / "workflow" / "reviewers" / f"{domain}.md"
    if custom.exists():
        return custom.read_text()
    return DEFAULT_PROFILES.get(domain, DEFAULT_PROFILES["code-reviewer"])


def build_reviewer_prompt(task: TaskSpec, worker_output: str) -> str:
    """Build structured reviewer prompt asking for PASS/FAIL + feedback."""
    instructions = "\n".join(f"- {i}" for i in task.instructions)
    return f"""Review the following worker output for this task.

## Task
Feature: {task.feature_name}
Description: {task.description}

Instructions the worker should have followed:
{instructions}

## Worker Output
{worker_output}

## Your Review
Respond with exactly PASS or FAIL on the first line.
Then provide specific, actionable feedback on the lines that follow.
If PASS: note what was done well and any minor suggestions.
If FAIL: list exactly what is wrong and what the worker must fix to pass.
"""


def parse_review_response(response: str) -> tuple[bool, str]:
    """Extract (passed, feedback) from reviewer LLM response.

    PASS/FAIL is determined by the first line. Everything else is feedback.
    Malformed responses (neither PASS nor FAIL) are treated as FAIL.
    """
    if not response or not response.strip():
        return False, "Reviewer returned empty response"
    lines = response.strip().splitlines()
    first = lines[0].strip().upper()
    feedback = "\n".join(lines[1:]).strip() if len(lines) > 1 else response.strip()
    passed = first.startswith("PASS")
    return passed, feedback
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_reviewer.py -v 2>&1
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runtime/reviewer.py tests/test_reviewer.py
git commit -m "feat: add profile loading, prompt builder, response parser to reviewer.py"
```

---

## Task 4: `runtime/reviewer.py` — `call_reviewer` function

**Files:**
- Modify: `runtime/reviewer.py`
- Modify: `tests/test_reviewer.py`

- [ ] **Step 1: Add test for `call_reviewer` (mocked LLM)**

Append to `tests/test_reviewer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reviewer.py -v -k "call_reviewer" 2>&1
```

Expected: `ImportError` on `call_reviewer`.

- [ ] **Step 3: Add `call_reviewer` to `runtime/reviewer.py`**

Append to `runtime/reviewer.py`:

```python
def call_reviewer(
    task: TaskSpec,
    worker_output: str,
    cfg: LLMConfig,
    project_root: Path,
) -> ReviewResult:
    """Run reviewer LLM, return ReviewResult. On LLM failure, returns PASS to avoid blocking."""
    domain = detect_domain(task)
    system = load_reviewer_profile(domain, project_root)
    prompt = build_reviewer_prompt(task, worker_output)

    response = call_llm(prompt, cfg, system=system)

    if response is None:
        print(f"[reviewer] LLM unavailable ({cfg.model}) — treating as PASS")
        return ReviewResult(passed=True, feedback="Reviewer LLM unavailable — skipped", domain=domain, model=cfg.model)

    passed, feedback = parse_review_response(response)
    verdict = "PASS" if passed else "FAIL"
    print(f"[reviewer] {verdict} ({domain}/{cfg.model}): {feedback[:80]}")
    return ReviewResult(passed=passed, feedback=feedback, domain=domain, model=cfg.model)
```

- [ ] **Step 4: Run all reviewer tests**

```bash
pytest tests/test_reviewer.py -v 2>&1
```

Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runtime/reviewer.py tests/test_reviewer.py
git commit -m "feat: add call_reviewer to reviewer.py"
```

---

## Task 5: `config.py` — add `reviewers` to `WorkflowConfig`

**Files:**
- Modify: `runtime/config.py`
- Create: `tests/test_config_reviewer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config_reviewer.py`:

```python
import tempfile
from pathlib import Path
import pytest
from workflow_kit.runtime.config import load_config, WorkflowConfig


MINIMAL_YAML = """
project:
  name: test-project
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

YAML_WITH_REVIEWER = MINIMAL_YAML + """
reviewers:
  - endpoint: https://api.anthropic.com/v1/messages
    api_key: sk-test
    model: claude-sonnet-4-6
"""

YAML_WITH_PER_TASK_REVIEWER = MINIMAL_YAML + """
reviewers:
  endpoint: https://api.anthropic.com/v1/messages
  api_key: sk-test
  model: claude-haiku-4-5
"""


def _write_yaml(content: str) -> Path:
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "workflow.yaml").write_text(content)
    return Path(tmp)


def test_load_config_no_reviewers_defaults_to_empty_list():
    root = _write_yaml(MINIMAL_YAML)
    cfg = load_config(root)
    assert cfg.reviewers == []


def test_load_config_reviewers_list_parsed():
    root = _write_yaml(YAML_WITH_REVIEWER)
    cfg = load_config(root)
    assert len(cfg.reviewers) == 1
    assert cfg.reviewers[0].model == "claude-sonnet-4-6"
    assert cfg.reviewers[0].endpoint == "https://api.anthropic.com/v1/messages"


def test_load_config_reviewer_single_dict_parsed():
    root = _write_yaml(YAML_WITH_PER_TASK_REVIEWER)
    cfg = load_config(root)
    assert len(cfg.reviewers) == 1
    assert cfg.reviewers[0].model == "claude-haiku-4-5"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_reviewer.py -v 2>&1
```

Expected: `TypeError` or `AttributeError` — `WorkflowConfig` has no `reviewers` field.

- [ ] **Step 3: Update `runtime/config.py`**

In `WorkflowConfig` dataclass, add field after `workers`:

```python
@dataclass
class WorkflowConfig:
    project: ProjectConfig
    orchestrators: list[LLMConfig]
    workers: list[LLMConfig]
    reviewers: list[LLMConfig]          # NEW — empty = reviewer disabled
    settings: Settings
    root: Path = field(default_factory=Path)
```

In `load_config()`, add reviewer parsing after workers (before `p = raw["project"]` line, after worker_raw block):

```python
    # Reviewers — optional, defaults to empty list
    reviewer_raw = raw.get("reviewers", raw.get("reviewer", None))
    reviewers = _parse_llm_list(reviewer_raw, default_timeout=120) if reviewer_raw else []
```

Update the `WorkflowConfig(...)` constructor call at the bottom of `load_config()`:

```python
    return WorkflowConfig(
        project=ProjectConfig(
            name=p["name"],
            description=p.get("description", ""),
            root=p.get("root", "."),
        ),
        orchestrators=orchestrators,
        workers=workers,
        reviewers=reviewers,            # NEW
        settings=Settings(
            work_hours=s.get("work_hours", "9-21"),
            auto_commit=bool(s.get("auto_commit", True)),
            verify_syntax=bool(s.get("verify_syntax", True)),
            max_retries=int(s.get("max_retries", 2)),
            dashboard_port=int(s.get("dashboard_port", 7860)),
        ),
        root=project_root.resolve(),
    )
```

- [ ] **Step 4: Run config tests**

```bash
pytest tests/test_config_reviewer.py -v 2>&1
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run all existing tests to verify no regressions**

```bash
pytest tests/ -v 2>&1
```

Expected: all previously passing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add runtime/config.py tests/test_config_reviewer.py
git commit -m "feat: add reviewers field to WorkflowConfig"
```

---

## Task 6: `context.py` — add `reviewer` field to `TaskSpec`

**Files:**
- Modify: `runtime/context.py`
- Modify: `tests/test_config_reviewer.py`

- [ ] **Step 1: Add test for TaskSpec reviewer field**

Append to `tests/test_config_reviewer.py`:

```python
from workflow_kit.runtime.context import TaskSpec


def test_task_spec_reviewer_defaults_to_none():
    task = TaskSpec(
        task_id="feat-001", type="implement", feature_name="Test",
        description="test", files_to_modify=[], context_files=[], instructions=[]
    )
    assert task.reviewer is None


def test_task_spec_reviewer_accepts_dict():
    task = TaskSpec(
        task_id="feat-001", type="implement", feature_name="Test",
        description="test", files_to_modify=[], context_files=[], instructions=[],
        reviewer={"endpoint": "https://api.openai.com/v1", "api_key": "sk-x", "model": "gpt-4o"}
    )
    assert task.reviewer["model"] == "gpt-4o"
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/test_config_reviewer.py -v -k "reviewer" 2>&1
```

Expected: `TypeError: __init__() got an unexpected keyword argument 'reviewer'`

- [ ] **Step 3: Update `runtime/context.py` — add `reviewer` to `TaskSpec`**

Add after the `result: Optional[dict] = None` line:

```python
    reviewer: Optional[dict] = None     # per-task reviewer LLMConfig override
```

Also add `Optional` to imports if not present — `context.py` line 9 already imports it.

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v 2>&1
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add runtime/context.py tests/test_config_reviewer.py
git commit -m "feat: add optional reviewer field to TaskSpec"
```

---

## Task 7: `dispatcher.py` — reviewer gate integration

**Files:**
- Modify: `runtime/dispatcher.py`
- Create: `tests/test_dispatcher_reviewer.py`

- [ ] **Step 1: Write failing tests for `_resolve_reviewer_cfg` and the gate**

Create `tests/test_dispatcher_reviewer.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_dispatcher_reviewer.py -v 2>&1
```

Expected: `ImportError` on `_resolve_reviewer_cfg`.

- [ ] **Step 3: Add `_resolve_reviewer_cfg` to `runtime/dispatcher.py`**

Add after the imports block (before `_is_work_hours`):

```python
from workflow_kit.runtime.reviewer import call_reviewer


def _resolve_reviewer_cfg(
    task: "TaskSpec", cfg: "WorkflowConfig"
) -> Optional["LLMConfig"]:
    """Return reviewer LLMConfig: per-task override → global fallback → None (skip)."""
    if task.reviewer:
        return LLMConfig(**task.reviewer)
    if cfg.reviewers:
        return cfg.reviewers[0]
    return None
```

- [ ] **Step 4: Run resolver tests**

```bash
pytest tests/test_dispatcher_reviewer.py -v 2>&1
```

Expected: all 3 resolver tests PASS.

- [ ] **Step 5: Insert reviewer gate into `run_one_cycle()` in `runtime/dispatcher.py`**

Find the block starting at line ~247 (`if not all_errors:`) and replace it:

```python
    if not all_errors:
        # Reviewer gate — only runs if reviewer is configured
        reviewer_cfg = _resolve_reviewer_cfg(task, cfg)
        if reviewer_cfg and response:
            review = call_reviewer(task, response, reviewer_cfg, project_root)
            ctx.append_decision(
                f"Review [{review.domain}/{review.model}]: "
                f"{'PASS' if review.passed else 'FAIL'} — {review.feedback[:120]}"
            )
            if not review.passed:
                if retry < cfg.settings.max_retries:
                    all_errors.append(f"[Reviewer FAIL] {review.feedback}")
                    # Fall through — existing retry loop re-calls worker with feedback
                else:
                    task.status = "failed"
                    task.error = f"Reviewer escalation after {cfg.settings.max_retries} retries: {review.feedback}"
                    ctx.move_task(task.task_id, "active", "completed")
                    ctx.write_task(task, "completed")
                    ctx.save_current(active_task=None)
                    print(f"  ⚠️  {task.task_id} ESCALATED — reviewer kept failing")
                    return True

    if not all_errors:
        task.status = "completed"
        task.result = {"files_modified": task.files_to_modify}
        if cfg.settings.auto_commit:
            git_commit(f"feat: {task.feature_name}", task.files_to_modify, project_root)
        ctx.append_decision(f"Completed: {task.feature_name} via {cfg.workers[0].model} chain")
        print(f"  ✅ {task.task_id} COMPLETED")
        try:
            orch_module.plan_next_tasks(cfg.orchestrators, project_root, n=1)
        except RuntimeError as e:
            print(f"  [orchestrator] Skipped: {e}")
    else:
        for fpath, content in originals.items():
            (project_root / fpath).write_text(content)
        task.status = "failed"
        task.error = "; ".join(all_errors[:3])
        print(f"  ❌ {task.task_id} FAILED: {task.error}")

    ctx.move_task(task.task_id, "active", "completed")
    ctx.write_task(task, "completed")
    ctx.save_current(active_task=None)
    return True
```

**Important:** Remove the old `if not all_errors: ... else: ... ctx.move_task(...)` block that was there before (lines ~247-271 in original) — the above replaces it entirely.

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v 2>&1
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add runtime/dispatcher.py tests/test_dispatcher_reviewer.py
git commit -m "feat: insert reviewer gate into dispatcher run_one_cycle"
```

---

## Task 8: Update skills and README

**Files:**
- Modify: `skills/init/SKILL.md`
- Modify: `skills/execute/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update `skills/init/SKILL.md` — add reviewer LLM setup phase**

Find Phase 7 (LLM setup) in `skills/init/SKILL.md` and add after it:

```markdown
## Phase 7b: Reviewer LLM setup

Ask:
> "Do you want to configure a **reviewer LLM** — a separate model that validates each worker output before marking tasks complete? This eliminates sycophancy bias when the same model reviews its own work.
> A) Yes — use a cloud API (Claude/OpenAI/OpenRouter) as reviewer, local model as worker
> B) Yes — use the same endpoint as worker (simpler, still adds review step)
> C) No — skip reviewer (worker output is accepted after syntax check only)"

**Path A or B:** Add `reviewers:` section to `workflow.yaml`:

```yaml
reviewers:
  - endpoint: "<chosen endpoint>"
    api_key: "<key or ${VAR}>"
    model: "<model name>"
```

**Path C:** Skip — no `reviewers:` key in workflow.yaml.
```

- [ ] **Step 2: Update `skills/execute/SKILL.md` — document reviewer flow**

Find the section describing the execute loop and update the task flow description to include:

```markdown
## Reviewer gate

After each worker output passes syntax verification:
1. If `reviewers:` is configured in `workflow.yaml` (or per-task `reviewer:` field), a reviewer agent is called
2. Reviewer responds with PASS or FAIL + feedback
3. On FAIL: feedback is appended to the retry prompt — worker tries again (up to `max_retries`)
4. After `max_retries` FAILs: task is escalated to user with reviewer's final feedback
5. On PASS (or no reviewer configured): task is marked completed and committed
```

- [ ] **Step 3: Update `README.md` — document `reviewers:` in workflow.yaml reference**

Find the `### Minimal` yaml block in the Configuration section and add `reviewers:` after `worker:`:

```yaml
# Optional: separate reviewer LLM (recommended for bias-free review)
reviewers:
  - endpoint: "https://api.anthropic.com/v1/messages"
    api_key: "${ANTHROPIC_API_KEY}"
    model: "claude-haiku-4-5-20251001"
```

Also update the Settings reference table to mention that `reviewer:` field on individual task JSONs overrides the global reviewer.

- [ ] **Step 4: Run full test suite one final time**

```bash
pytest tests/ -v 2>&1
```

Expected: all tests PASS.

- [ ] **Step 5: Final commit**

```bash
git add skills/init/SKILL.md skills/execute/SKILL.md README.md
git commit -m "docs: document reviewer setup in init skill, execute skill, and README"
```

---

## Self-Review

**Spec coverage check:**
- ✅ ReviewResult dataclass → Task 2
- ✅ detect_domain keyword scoring → Task 2
- ✅ DEFAULT_PROFILES for all 6 domains → Task 3
- ✅ load_reviewer_profile (custom file fallback) → Task 3
- ✅ build_reviewer_prompt → Task 3
- ✅ parse_review_response (PASS/FAIL + malformed) → Task 3
- ✅ call_reviewer (LLM failure → PASS) → Task 4
- ✅ WorkflowConfig.reviewers list → Task 5
- ✅ TaskSpec.reviewer per-task override → Task 6
- ✅ _resolve_reviewer_cfg lookup order → Task 7
- ✅ Reviewer gate in run_one_cycle → Task 7
- ✅ Escalation after max_retries → Task 7
- ✅ Backward compatible (no reviewers = skip) → Task 5 + 7
- ✅ Skills + README docs → Task 8

**Type consistency:**
- `call_reviewer` takes `(TaskSpec, str, LLMConfig, Path)` → consistent across Tasks 4 and 7
- `ReviewResult.passed: bool` → consistent in all uses
- `_resolve_reviewer_cfg` returns `Optional[LLMConfig]` → checked in Task 7 before use

**No placeholders:** confirmed — all steps have concrete code.
