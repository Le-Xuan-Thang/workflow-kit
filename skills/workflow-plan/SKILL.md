---
name: workflow-plan
description: Ask DeepSeek to read goals.md and the worker capability profile, then create the next 3–5 task JSONs in .workflow/tasks/pending/. Run after workflow-init and after editing goals.md.
---

# Workflow Plan

Call the orchestrator (DeepSeek) to plan the next batch of tasks. The orchestrator reads your goals, the worker's capability profile, and completed task history — then writes task JSONs to `.workflow/tasks/pending/`.

<HARD-GATE>
Do NOT call the orchestrator if `.workflow/worker_capability.json` is missing. The orchestrator MUST know the worker's capability before planning. Tell the user to run `/workflow-kit:workflow-init` first.
</HARD-GATE>

## Steps

### Step 1: Verify prerequisites
Check that all three exist:
- `workflow.yaml` — if missing: "Run /workflow-kit:workflow-init first."
- `goals.md` — if missing or empty: "Edit goals.md with your project goals first."
- `.workflow/worker_capability.json` — if missing: "Run /workflow-kit:workflow-init to benchmark the worker first."

### Step 2: Read context
- Load `workflow.yaml` for orchestrator config
- Read `goals.md`
- Read up to 10 most recent completed task summaries from `.workflow/tasks/completed/` (sort by `completed_at` desc)
- Read `.workflow/memory/decisions.md` (last 20 lines)
- Read `.workflow/worker_capability.json`

### Step 3: Call orchestrator
```bash
python -m workflow_kit plan
```

This calls DeepSeek with capability summary injected. The orchestrator:
- Decomposes goals into 3–5 concrete tasks
- Matches task complexity to worker skill scores
- Decomposes any task requiring a skill score < 3.0 into smaller sub-tasks using stronger skills
- Writes task JSONs to `.workflow/tasks/pending/`

### Step 4: Report
Print the planned tasks inline:
```
Planned N tasks → .workflow/tasks/pending/

  feat-001  Add CSV export endpoint           (code_gen 4.2 ✓)
  feat-002  Add Export CSV button to toolbar  (frontend_js 3.5 ✓)
  feat-003  Write unit tests for export       (code_gen 4.2 ✓)

Review tasks in .workflow/tasks/pending/ then run /workflow-kit:workflow-start.
```

If a task was decomposed due to low skill score, show:
```
  fix-001a  Read broken line in export.py     (code_edit 3.8 ✓)  ← decomposed from bug_fix 2.9
  fix-001b  Replace with correct pattern      (code_edit 3.8 ✓)
```
