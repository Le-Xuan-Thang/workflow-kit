"""Task planner. Always reads worker capability before planning."""
from __future__ import annotations

import json
import re
from pathlib import Path

from workflow_kit.runtime.config import LLMConfig
from workflow_kit.runtime.context import WorkflowContext, TaskSpec
from workflow_kit.runtime.worker import call_llm_with_fallback


def _build_planning_prompt(
    project_root: Path,
    capability: dict,
    completed: list[str],
    n: int,
) -> str:
    goals_path = project_root / "goals.md"
    goals = goals_path.read_text() if goals_path.exists() else "(no goals.md found)"

    skill_lines = "\n".join(
        f"  {k}: {v}/5" for k, v in capability.get("skills", {}).items()
    )
    completed_block = "\n".join(f"  - {s}" for s in completed) or "  (none yet)"

    return f"""You are an orchestrator planning tasks for an AI worker.

## Worker capability
Model: {capability.get('model', 'unknown')}
{skill_lines}

Summary: {capability.get('summary', '')}

## Rules for planning (MANDATORY)
- Only assign tasks that use skills scoring >= 3.0
- For skills below 3.0 (e.g. bug_fix={capability.get('skills', {}).get('bug_fix', '?')}, refactor={capability.get('skills', {}).get('refactor', '?')}):
  decompose into smaller tasks using stronger skills (code_edit, code_gen)
- Each task must modify at most 2 files
- Instructions must be explicit: include exact function names, routes, variable names
- Do NOT assign vague tasks like "improve X" or "refactor Y"

## Project goals
{goals}

## Already completed
{completed_block}

## Your output
Return a JSON array of exactly {n} task(s). Each task must have these fields:
  task_id (string, kebab-case, unique, starts with feat-NNN),
  type ("implement"),
  feature_name (string),
  description (string),
  files_to_modify (list of relative file paths),
  context_files (list of relative file paths to read for context),
  instructions (list of specific implementation steps)

Output ONLY the JSON array. No explanation, no markdown, just the array.
"""


def _parse_tasks(response: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    # Try direct parse first
    try:
        data = json.loads(response.strip())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", response, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding bare array in response
    m = re.search(r"\[.*\]", response, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return []


def plan_next_tasks(
    orchestrator_cfgs: list[LLMConfig],
    project_root: Path,
    n: int = 3,
) -> list[TaskSpec]:
    """Call the orchestrator chain to plan the next n tasks.

    Tries ``orchestrator_cfgs[0]`` (primary) first; falls back to subsequent
    entries if the primary fails or returns no response.

    Raises RuntimeError if worker_capability.json does not exist.
    """
    ctx = WorkflowContext(project_root)
    ctx.ensure_dirs()

    capability = ctx.load_capability()
    if capability is None:
        raise RuntimeError(
            "worker_capability.json not found in .workflow/. "
            "Run: python -m workflow_kit benchmark"
        )

    completed = ctx.completed_task_summaries(limit=10)
    prompt = _build_planning_prompt(project_root, capability, completed, n)

    primary_model = orchestrator_cfgs[0].model if orchestrator_cfgs else "unknown"
    print(f"[orchestrator] Planning {n} task(s) (primary: {primary_model})...")
    response = call_llm_with_fallback(prompt, orchestrator_cfgs)

    if not response:
        print("[orchestrator] No response from any orchestrator model")
        return []

    raw_tasks = _parse_tasks(response)
    if not raw_tasks:
        print(f"[orchestrator] Could not parse task JSON from response:\n{response[:300]}")
        return []

    tasks = []
    for raw in raw_tasks[:n]:
        try:
            task = TaskSpec(
                task_id=raw["task_id"],
                type=raw.get("type", "implement"),
                feature_name=raw["feature_name"],
                description=raw["description"],
                files_to_modify=raw.get("files_to_modify", []),
                context_files=raw.get("context_files", []),
                instructions=raw.get("instructions", []),
            )
            ctx.write_task(task, "pending")
            tasks.append(task)
            print(f"[orchestrator] Queued: {task.task_id} — {task.feature_name}")
        except (KeyError, TypeError) as e:
            print(f"[orchestrator] Skipping malformed task: {e}")

    return tasks
