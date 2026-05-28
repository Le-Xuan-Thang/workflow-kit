---
name: workflow-init
description: Initialize workflow-kit in a project. Run once to create workflow.yaml, goals.md, .workflow/ state dirs, and benchmark the worker model. Must run before workflow-plan or workflow-start.
---

# Workflow Init

Set up workflow-kit in the current project and benchmark the worker model so the orchestrator knows what it can assign.

<HARD-GATE>
Do NOT run the benchmark or write any files until you have confirmed the orchestrator and worker endpoints/models with the user. These are the only required inputs — everything else uses defaults.
</HARD-GATE>

## Steps

### Step 1: Detect project root
Walk up from `cwd` until you find a `.git` directory, `pyproject.toml`, or `package.json`. That is `PROJECT_ROOT`.

### Step 2: Check existing config
If `workflow.yaml` already exists at `PROJECT_ROOT`, read it and ask: "workflow.yaml already exists — update it, or keep and skip to benchmark?"

### Step 3: Collect config (ask the user)
Ask for these values, one message — defaults shown:

| Field | Default |
|---|---|
| Orchestrator model | `deepseek/deepseek-chat:free` |
| Orchestrator endpoint | `https://openrouter.ai/api/v1/chat/completions` |
| Orchestrator API key | `${OPENROUTER_API_KEY}` |
| Worker model | `llama3.1:70b` |
| Worker endpoint | `http://localhost:11434/v1/chat/completions` |
| Worker API key | `ollama` |
| Work hours | `9-21` |

### Step 4: Write workflow.yaml
```yaml
project:
  name: "<detected from pyproject.toml / package.json / dir name>"
  description: "<one-line from pyproject.toml description or ask user>"
  root: "."

orchestrator:
  endpoint: "<value>"
  api_key: "<value>"
  model: "<value>"

worker:
  endpoint: "<value>"
  api_key: "<value>"
  model: "<value>"

settings:
  work_hours: "<value>"
  auto_commit: true
  verify_syntax: true
  max_retries: 2
  dashboard_port: 7860
```

### Step 5: Write goals.md (if missing)
```markdown
# Project Goals

List your high-level goals here in plain English.
The orchestrator (DeepSeek) will read this file to plan tasks.

Example:
- Add dark mode toggle to the webapp
- Fix the CSV export to include confidence scores
- Add unit tests for the inference pipeline
```

### Step 6: Create .workflow/ directories
```
.workflow/
├── tasks/pending/
├── tasks/active/
├── tasks/completed/
└── memory/
```

### Step 7: Update .gitignore
Append to `.gitignore` if not already present:
```
.workflow/
workflow.yaml
```
(If API keys are not inline — i.e., all values use `${ENV_VAR}` — only `.workflow/` needs gitignoring. Inform the user.)

### Step 8: Run benchmark
```bash
python -m workflow_kit benchmark
```
This profiles the worker model across 7 skill areas (code_gen, code_edit, bug_fix, frontend_js, css_styling, api_design, refactor). Takes 2–5 minutes. Print the capability summary when done so the user can see what the worker is strong and weak at.

### Step 9: Report
Print:
```
✓ workflow.yaml written
✓ goals.md created (edit it with your goals before running /workflow-plan)
✓ .workflow/ state dirs created
✓ Worker profiled → .workflow/worker_capability.json

Worker: <model>
Capability: <summary from capability file>

Next steps:
  1. Edit goals.md with your project goals
  2. Run /workflow-kit:workflow-plan to let DeepSeek plan tasks
  3. Run /workflow-kit:workflow-start to begin the automated loop
```

## Re-benchmark flag
If the user passes `--rebenchmark` or says "re-run benchmark", skip Steps 1–7 and go straight to Step 8.
