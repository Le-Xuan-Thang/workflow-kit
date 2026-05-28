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

YAML_WITH_SINGLE_REVIEWER = MINIMAL_YAML + """
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
    root = _write_yaml(YAML_WITH_SINGLE_REVIEWER)
    cfg = load_config(root)
    assert len(cfg.reviewers) == 1
    assert cfg.reviewers[0].model == "claude-haiku-4-5"


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
