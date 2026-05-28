# Cross-Provider Reviewer — Design Spec
_Date: 2026-05-28_

## Summary

Add a mandatory reviewer agent step after each worker output. The reviewer uses a separate LLM endpoint (different provider/model than the worker) to eliminate sycophancy bias. Reviewer issues PASS/FAIL + feedback; worker retries on FAIL. No reviewer = backward compatible (task passes as before).

---

## Architecture & Data Flow

```
dispatcher.run_one_cycle()
    │
    ├─► worker: call_llm_with_fallback(prompt, cfg.workers)
    │       │
    │       ▼
    │   apply_surgical_edit() + verify_syntax()
    │       │
    │       ▼ (syntax OK)
    ├─► reviewer: call_reviewer(task, worker_output, reviewer_cfg, project_root)
    │       │
    │       ├─ PASS → mark completed, git commit
    │       └─ FAIL → append feedback to all_errors → retry worker loop
    │                   └─ still FAIL after max_retries → escalate to user
    └─► (no reviewer config) → skip, mark completed  ← backward compatible
```

**ReviewResult:**
```python
@dataclass
class ReviewResult:
    passed: bool
    feedback: str   # always logged, even on PASS
    domain: str     # detected reviewer profile
    model: str      # model that reviewed
```

---

## New Module: `runtime/reviewer.py`

### Domain Detection

Keyword scoring from `task.type + task.description + task.feature_name`:

| Domain | Keywords |
|---|---|
| `code-reviewer` | code, feature, bugfix, refactor, function, class, api, implement |
| `editor` | doc, readme, article, write, text, markdown, comment |
| `researcher` | research, analysis, literature, survey, study, paper |
| `designer` | ui, schema, architecture, design, layout, interface |
| `data-scientist` | data, ml, model, pipeline, dataset, train |
| `devops` | deploy, infra, ci, docker, k8s, cloud, pipeline |

Falls back to `code-reviewer` when no clear winner.

### Profile Loading

1. Check `workflow/reviewers/<domain>.md` — user-editable custom profile
2. Fall back to `DEFAULT_PROFILES[domain]` — hardcoded sensible defaults

### Reviewer Prompt

Structured prompt asking the reviewer to:
1. Evaluate worker output against task spec
2. Return exactly `PASS` or `FAIL` on the first line
3. Follow with specific, actionable feedback

### Response Parsing

`parse_review_response(response)` extracts:
- `passed = response.strip().upper().startswith("PASS")`
- `feedback = everything after the first line`

---

## Config Changes

### `workflow.yaml` — new optional `reviewers:` section

```yaml
# Global reviewer (optional — omit to skip reviewer entirely)
reviewers:
  - endpoint: "https://api.anthropic.com/v1/messages"
    api_key: "${ANTHROPIC_API_KEY}"
    model: "claude-sonnet-4-6"

# Per-task override (in task JSON under workflow/tasks/pending/<id>.json):
# { "reviewer": { "endpoint": "...", "api_key": "...", "model": "..." } }
```

Accepts single dict or list (same pattern as `workers`/`orchestrators`).

### `config.py` — `WorkflowConfig`

```python
@dataclass
class WorkflowConfig:
    project: ProjectConfig
    orchestrators: list[LLMConfig]
    workers: list[LLMConfig]
    reviewers: list[LLMConfig]   # NEW — empty list = reviewer disabled
    settings: Settings
```

Parser: optional, defaults to `[]`.

### `context.py` — `TaskSpec`

```python
@dataclass
class TaskSpec:
    ...
    reviewer: Optional[dict] = None   # NEW — per-task LLMConfig override
```

---

## `dispatcher.py` — Integration

**Reviewer config resolution** (new helper):

```python
def _resolve_reviewer_cfg(task: TaskSpec, cfg: WorkflowConfig) -> Optional[LLMConfig]:
    if task.reviewer:
        return LLMConfig(**task.reviewer)
    if cfg.reviewers:
        return cfg.reviewers[0]
    return None
```

**`run_one_cycle()` — reviewer gate inserted after syntax check passes:**

```python
if not all_errors:
    reviewer_cfg = _resolve_reviewer_cfg(task, cfg)
    if reviewer_cfg:
        result = call_reviewer(task, response, reviewer_cfg, project_root)
        ctx.append_decision(
            f"Review [{result.domain}/{result.model}]: "
            f"{'PASS' if result.passed else 'FAIL'} — {result.feedback[:120]}"
        )
        if not result.passed:
            if retry < cfg.settings.max_retries:
                all_errors.append(f"[Reviewer FAIL] {result.feedback}")
                # existing retry loop handles re-calling worker with feedback
            else:
                task.error = f"Reviewer escalation after {cfg.settings.max_retries} retries: {result.feedback}"
                ctx.move_task(task.task_id, "active", "completed")
                ctx.write_task(task, "completed")
                print(f"  ⚠️  {task.task_id} ESCALATED")
                return True
```

Reviewer feedback is injected into `all_errors` — the existing retry loop re-calls the worker with the feedback appended to the prompt. No new retry logic needed.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `runtime/reviewer.py` | **CREATE** — `detect_domain`, `load_reviewer_profile`, `build_reviewer_prompt`, `parse_review_response`, `call_reviewer`, `DEFAULT_PROFILES`, `ReviewResult` |
| `runtime/config.py` | Add `reviewers: list[LLMConfig]` to `WorkflowConfig`, parse optional `reviewers` section |
| `runtime/context.py` | Add `reviewer: Optional[dict] = None` to `TaskSpec` |
| `runtime/dispatcher.py` | Add `_resolve_reviewer_cfg()`, insert reviewer gate in `run_one_cycle()`, import from `reviewer` |
| `skills/init/SKILL.md` | Add Phase for reviewer LLM setup in wizard |
| `skills/execute/SKILL.md` | Update to mention reviewer step and escalation flow |
| `README.md` | Update workflow.yaml docs with `reviewers:` section |

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Reviewer LLM call fails (network/timeout) | Log warning, treat as PASS (don't block task on reviewer outage) |
| Response is neither PASS nor FAIL | Treat as FAIL with feedback = full response |
| `reviewers: []` in config | Skip reviewer entirely — backward compatible |
| Per-task `reviewer` has invalid keys | Raise `ConfigError` at task load time |

---

## Non-Goals

- Reviewer cannot edit or patch worker output
- No multi-reviewer consensus (one reviewer per task)
- No reviewer for non-code tasks unless user adds `reviewers:` config
