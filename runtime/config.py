"""Load and validate workflow.yaml. Resolve ${ENV_VAR} references."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise ImportError("pyyaml required: uv add pyyaml")

from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass
class ProjectConfig:
    name: str
    description: str
    root: str = "."


@dataclass
class LLMConfig:
    endpoint: str
    api_key: str
    model: str
    timeout: int = 120


@dataclass
class Settings:
    work_hours: str = "9-21"
    auto_commit: bool = True
    verify_syntax: bool = True
    max_retries: int = 2
    dashboard_port: int = 7860


@dataclass
class WorkflowConfig:
    project: ProjectConfig
    orchestrators: list[LLMConfig]
    workers: list[LLMConfig]
    settings: Settings
    root: Path = field(default_factory=Path)

    # Backward-compat: single-model access
    @property
    def orchestrator(self) -> LLMConfig:
        return self.orchestrators[0]

    @property
    def worker(self) -> LLMConfig:
        return self.workers[0]


def _resolve_env(value: Any) -> Any:
    """Replace ${VAR} with os.environ[VAR] in string values."""
    if not isinstance(value, str):
        return value

    def replacer(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var)
        if val is None:
            raise ConfigError(
                f"Environment variable '{var}' not set (referenced in workflow.yaml)"
            )
        return val

    return re.sub(r"\$\{([^}]+)\}", replacer, value)


def _resolve_value(v: Any) -> Any:
    """Recursively resolve ${ENV_VAR} in strings, dicts, and lists."""
    if isinstance(v, str):
        return _resolve_env(v)
    elif isinstance(v, dict):
        return {k: _resolve_value(val) for k, val in v.items()}
    elif isinstance(v, list):
        return [_resolve_value(item) for item in v]
    return v


def _resolve_dict(d: dict) -> dict:
    return {k: _resolve_value(v) for k, v in d.items()}


def _parse_llm_list(raw_section: Any, default_timeout: int) -> list[LLMConfig]:
    """Parse one LLM entry (dict) or a list of entries into LLMConfig list."""
    if isinstance(raw_section, dict):
        raw_section = [raw_section]
    result = []
    for e in raw_section:
        result.append(LLMConfig(
            endpoint=e["endpoint"],
            api_key=e["api_key"],
            model=e["model"],
            timeout=int(e.get("timeout", default_timeout)),
        ))
    return result


def load_config(project_root: Path) -> WorkflowConfig:
    """Load workflow.yaml from project_root. Raises ConfigError on any problem.

    Supports both singular keys (``worker``, ``orchestrator``) and plural lists
    (``workers``, ``orchestrators``).  Plural takes precedence.
    """
    load_dotenv(project_root / ".env", override=False)

    yaml_path = project_root / "workflow.yaml"
    if not yaml_path.exists():
        raise ConfigError(f"workflow.yaml not found in {project_root}")

    raw = yaml.safe_load(yaml_path.read_text())
    raw = _resolve_dict(raw)

    if "project" not in raw:
        raise ConfigError("workflow.yaml missing required section: 'project'")

    # Orchestrators — accept 'orchestrators' (list) or 'orchestrator' (single)
    if "orchestrators" not in raw and "orchestrator" not in raw:
        raise ConfigError(
            "workflow.yaml missing required section: 'orchestrators' (or 'orchestrator')"
        )
    orchestrator_raw = raw.get("orchestrators", raw.get("orchestrator"))
    orchestrators = _parse_llm_list(orchestrator_raw, default_timeout=120)

    # Workers — accept 'workers' (list) or 'worker' (single)
    if "workers" not in raw and "worker" not in raw:
        raise ConfigError(
            "workflow.yaml missing required section: 'workers' (or 'worker')"
        )
    worker_raw = raw.get("workers", raw.get("worker"))
    workers = _parse_llm_list(worker_raw, default_timeout=300)

    p = raw["project"]
    s = raw.get("settings", {})

    return WorkflowConfig(
        project=ProjectConfig(
            name=p["name"],
            description=p.get("description", ""),
            root=p.get("root", "."),
        ),
        orchestrators=orchestrators,
        workers=workers,
        settings=Settings(
            work_hours=s.get("work_hours", "9-21"),
            auto_commit=bool(s.get("auto_commit", True)),
            verify_syntax=bool(s.get("verify_syntax", True)),
            max_retries=int(s.get("max_retries", 2)),
            dashboard_port=int(s.get("dashboard_port", 7860)),
        ),
        root=project_root.resolve(),
    )
