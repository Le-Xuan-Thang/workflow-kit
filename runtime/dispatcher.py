"""Task executor. Picks tasks from pending/, calls worker, verifies, commits, loops."""
from __future__ import annotations

import ast
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from workflow_kit.runtime.config import WorkflowConfig
from workflow_kit.runtime.context import WorkflowContext, TaskSpec
from workflow_kit.runtime.worker import call_llm_with_fallback, parse_file_blocks
from workflow_kit.runtime import orchestrator as orch_module


def _is_work_hours(work_hours: str) -> bool:
    """Check if current hour is within work_hours range.

    Supports daytime ('9-21') and overnight ('21-9') ranges.
    Overnight: active when hour >= start OR hour < end.
    """
    try:
        start, end = (int(x) for x in work_hours.split("-"))
        hour = datetime.now().hour
        if start < end:
            return start <= hour < end  # daytime: e.g. 9-21
        else:
            return hour >= start or hour < end  # overnight: e.g. 21-9
    except Exception:
        return True


def verify_file(filepath: Path) -> list[str]:
    """Return list of syntax errors, empty list if file is valid."""
    errors = []
    if not filepath.exists():
        return []
    if filepath.suffix == ".py":
        try:
            ast.parse(filepath.read_text())
        except SyntaxError as e:
            errors.append(f"Syntax error in {filepath.name}: {e}")
    elif filepath.suffix == ".js":
        result = subprocess.run(
            ["node", "--check", str(filepath)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            errors.append(f"JS error in {filepath.name}: {result.stderr.strip()}")
    return errors


def apply_surgical_edit(filepath: Path, generated_code: str) -> bool:
    """Apply generated code to existing file by replacing named blocks in-place.

    If file doesn't exist, create it. If no named blocks found, append.
    """
    if not filepath.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(generated_code)
        return True

    content = filepath.read_text()
    new_functions = _extract_functions(generated_code)

    if not new_functions:
        content = content.rstrip() + "\n\n" + generated_code.strip() + "\n"
        filepath.write_text(content)
        return True

    modified = content
    for name, code in new_functions.items():
        loc = _find_function(modified, name)
        if loc:
            start, end = loc
            modified = modified[:start] + code + modified[end:]
            print(f"  Replaced function '{name}' in {filepath.name}")
        else:
            modified = modified.rstrip() + "\n\n" + code + "\n"
            print(f"  Appended new function '{name}' to {filepath.name}")

    filepath.write_text(modified)
    return True


def _extract_functions(code: str) -> dict[str, str]:
    """Extract {name: full_source} for each function/class in code string."""
    result = {}
    for m in re.finditer(
        r"(?:^|\n)((?:async\s+)?def\s+(\w+)[^\n]*\n(?:[ \t]+[^\n]*\n?)*)",
        code,
        re.MULTILINE,
    ):
        result[m.group(2)] = m.group(1).rstrip()
    for m in re.finditer(
        r"(?:^|\n)(class\s+(\w+)[^\n]*\n(?:[ \t]+[^\n]*\n?)*)",
        code,
        re.MULTILINE,
    ):
        if m.group(2) not in result:
            result[m.group(2)] = m.group(1).rstrip()
    return result


def _find_function(content: str, name: str) -> Optional[tuple[int, int]]:
    """Find start/end position of a named function/class in source string."""
    pattern = rf"(?:^|\n)((?:async\s+)?(?:def|class)\s+{re.escape(name)}\b)"
    m = re.search(pattern, content)
    if not m:
        return None
    start = m.start(1)
    # Find end: next def/class at top-level indent, or EOF
    lines = content[start:].split("\n")
    end_line = len(lines)
    for i, line in enumerate(lines[1:], 1):
        if line and not line[0].isspace() and line.strip():
            end_line = i
            break
    end = start + len("\n".join(lines[:end_line]))
    return (start, end)


def _build_worker_prompt(task: TaskSpec, project_root: Path) -> str:
    context_blocks = []
    for fpath in task.context_files:
        full = project_root / fpath
        if full.exists():
            content = full.read_text()[:4000]
            context_blocks.append(f"### {fpath}\n```\n{content}\n```")

    instructions = "\n".join(f"- {i}" for i in task.instructions)
    files_list = "\n".join(f"- {f}" for f in task.files_to_modify)

    return f"""Implement this feature using surgical edits:

Feature: {task.feature_name}
Description: {task.description}

Files to modify:
{files_list}

Instructions:
{instructions}

Context:
{"".join(context_blocks) or "(no context files)"}

Output ONLY the modified functions/classes for each file in this format:
**path/to/file.py**
```python
def function_name(...):
    ...
```

Output each function separately. Do NOT rewrite entire files. Do NOT include unchanged functions."""


def git_commit(message: str, files: list[str], project_root: Path):
    subprocess.run(["git", "add", "--"] + files, cwd=project_root, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message, "--allow-empty"],
        cwd=project_root,
        capture_output=True,
    )


def run_one_cycle(cfg: WorkflowConfig, project_root: Path) -> bool:
    """Pick one pending task, execute it, call orchestrator for next task.

    Returns True if a task was processed, False if queue was empty.
    """
    ctx = WorkflowContext(project_root)
    task = ctx.get_next_pending()
    if task is None:
        return False

    print(f"\n{'=' * 50}")
    print(f"Executing: {task.feature_name} ({task.task_id})")
    print(f"{'=' * 50}")

    ctx.move_task(task.task_id, "pending", "active")
    ctx.save_current(active_task=task.task_id, last_command=f"Execute: {task.feature_name}")

    # Save originals for rollback
    originals = {
        f: (project_root / f).read_text()
        for f in task.files_to_modify
        if (project_root / f).exists()
    }

    prompt = _build_worker_prompt(task, project_root)
    response = call_llm_with_fallback(prompt, cfg.workers)

    success = False
    all_errors: list[str] = []

    if response:
        file_blocks = parse_file_blocks(response)
        if not file_blocks:
            all_errors.append("Worker returned no file blocks")
        else:
            for fname, code in file_blocks.items():
                matched = next(
                    (
                        f
                        for f in task.files_to_modify
                        if fname == f or Path(fname).name == Path(f).name
                    ),
                    None,
                )
                if matched:
                    target = project_root / matched
                    apply_surgical_edit(target, code)
                    if cfg.settings.verify_syntax:
                        all_errors.extend(verify_file(target))
    else:
        all_errors.append("Worker returned no response")

    # Retry with error feedback if needed
    retry = 0
    while all_errors and retry < cfg.settings.max_retries:
        retry += 1
        print(f"  Retrying (attempt {retry}/{cfg.settings.max_retries})...")
        feedback = "\n".join(all_errors[:3])
        retry_prompt = prompt + f"\n\nPrevious attempt failed:\n{feedback}\n\nFix these errors."
        response = call_llm_with_fallback(retry_prompt, cfg.workers)
        all_errors = []
        if response:
            for fname, code in parse_file_blocks(response).items():
                matched = next(
                    (
                        f
                        for f in task.files_to_modify
                        if fname == f or Path(fname).name == Path(f).name
                    ),
                    None,
                )
                if matched:
                    apply_surgical_edit(project_root / matched, code)
                    if cfg.settings.verify_syntax:
                        all_errors.extend(verify_file(project_root / matched))

    if not all_errors:
        task.status = "completed"
        task.result = {"files_modified": task.files_to_modify}
        success = True
        if cfg.settings.auto_commit:
            git_commit(f"feat: {task.feature_name}", task.files_to_modify, project_root)
        ctx.append_decision(f"Completed: {task.feature_name} via {cfg.workers[0].model} chain")
        print(f"  ✅ {task.task_id} COMPLETED")
        # Trigger orchestrator to queue the next task automatically
        try:
            orch_module.plan_next_tasks(cfg.orchestrators, project_root, n=1)
        except RuntimeError as e:
            print(f"  [orchestrator] Skipped: {e}")
    else:
        # Rollback modified files
        for fpath, content in originals.items():
            (project_root / fpath).write_text(content)
        task.status = "failed"
        task.error = "; ".join(all_errors[:3])
        print(f"  ❌ {task.task_id} FAILED: {task.error}")

    ctx.move_task(task.task_id, "active", "completed")
    ctx.write_task(task, "completed")
    ctx.save_current(active_task=None)
    return True


def watch(cfg: WorkflowConfig, project_root: Path):
    """Main loop: process tasks continuously, respecting work_hours."""
    print("[dispatcher] Watching for tasks in .workflow/tasks/pending/ ...")
    ctx = WorkflowContext(project_root)
    ctx.ensure_dirs()

    while True:
        if not _is_work_hours(cfg.settings.work_hours):
            print("[dispatcher] Outside work hours — sleeping 30 min")
            time.sleep(1800)
            continue

        if not run_one_cycle(cfg, project_root):
            time.sleep(5)
