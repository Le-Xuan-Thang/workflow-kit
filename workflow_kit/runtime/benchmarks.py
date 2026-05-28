"""Worker capability profiler. Runs YAML challenge definitions, scores responses."""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from workflow_kit.runtime.config import LLMConfig
from workflow_kit.runtime.worker import call_llm, call_llm_with_fallback

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "benchmarks"


def score_response(response: str, challenge: dict) -> float:
    """Score a single challenge response. Returns 0.0–1.0."""
    if not response:
        return 0.0

    patterns = challenge.get("required_patterns", [])
    must_compile = challenge.get("must_compile", False)

    # Syntax check for Python only
    if must_compile:
        try:
            ast.parse(response)
        except SyntaxError:
            return 0.0

    if not patterns:
        return 1.0

    matched = sum(1 for p in patterns if p in response)
    return matched / len(patterns)


def _load_challenges(skill: str) -> list[dict]:
    path = BENCHMARKS_DIR / f"{skill}.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    return data.get("challenges", [])


def call_llm_orchestrator(prompt: str, cfgs: list[LLMConfig]) -> Optional[str]:
    """Thin wrapper so tests can mock orchestrator calls separately."""
    return call_llm_with_fallback(prompt, cfgs)


def run_benchmark(
    worker_cfg: LLMConfig,
    orchestrator_cfgs: list[LLMConfig],
    project_root: Path,
) -> dict:
    """Run all benchmark challenges against worker_cfg. Returns capability profile dict."""
    skills = [
        "code_gen",
        "code_edit",
        "bug_fix",
        "frontend_js",
        "css_styling",
        "api_design",
        "refactor",
    ]

    skill_scores: dict[str, float] = {}

    for skill in skills:
        challenges = _load_challenges(skill)
        if not challenges:
            skill_scores[skill] = 3.0  # default if no challenges defined
            continue

        total = 0.0
        for ch in challenges:
            response = call_llm(ch["prompt"], worker_cfg)
            total += score_response(response or "", ch) * ch.get("score", 1.0)
        max_score = sum(ch.get("score", 1.0) for ch in challenges)
        raw = (total / max_score) * 5.0 if max_score > 0 else 0.0
        skill_scores[skill] = round(min(5.0, raw), 2)

    overall = round(sum(skill_scores.values()) / len(skill_scores), 2)

    # Ask orchestrator to interpret scores as plain English
    scores_text = "\n".join(f"  {k}: {v}/5" for k, v in skill_scores.items())
    summary_prompt = (
        f"A worker LLM ({worker_cfg.model}) scored as follows on coding skill benchmarks:\n"
        f"{scores_text}\n\n"
        f"Write 2-3 sentences summarising what tasks this worker is good at, "
        f"what it struggles with, and what the orchestrator should watch out for "
        f"when planning tasks. Be specific and actionable. No bullet points."
    )
    summary = call_llm_orchestrator(summary_prompt, orchestrator_cfgs) or (
        "Worker capability benchmarked. See skill scores for details."
    )

    profile = {
        "model": worker_cfg.model,
        "benchmarked_at": datetime.now(timezone.utc).isoformat(),
        "skills": skill_scores,
        "overall": overall,
        "summary": summary,
    }

    # Persist to .workflow/
    from workflow_kit.runtime.context import WorkflowContext

    ctx = WorkflowContext(project_root)
    ctx.ensure_dirs()
    ctx.save_capability(profile)

    return profile
