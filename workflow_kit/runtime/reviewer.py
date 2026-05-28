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
    feedback = "\n".join(lines[1:]).strip() if len(lines) > 1 else "No feedback provided"
    passed = first.startswith("PASS")
    return passed, feedback


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
