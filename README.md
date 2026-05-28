# workflow-kit

A portable **multi-agent development loop** that works as a superpowers-compatible plugin across Claude Code, Codex CLI, OpenCode, Gemini CLI, and any terminal.

**DeepSeek plans → local LLM executes → dispatcher loops automatically.**

You write goals in plain English. The orchestrator reads them, profiles your worker model's capabilities, and creates tasks it knows the worker can complete. The dispatcher runs the loop — committing each change — while you sleep.

---

## How it works

```
goals.md  (you write this)
    │
    ▼
/workflow-kit:workflow-init
    ├── Writes workflow.yaml
    ├── Creates .workflow/ state dirs
    └── Benchmarks worker model → .workflow/worker_capability.json
    │
    ▼
/workflow-kit:workflow-plan
    └── DeepSeek reads goals + capability profile
        → writes 3-5 task JSONs to .workflow/tasks/pending/
    │
    ▼
/workflow-kit:workflow-start
    └── Dispatcher loop (background):
        pick task → call worker LLM → apply edits → verify → git commit
        → plan next task → repeat
    │
    ▼
/workflow-kit:workflow-status   (quick inline check)
/workflow-kit:workflow-monitor  (live TUI or web dashboard)
```

---

## Prerequisites

| Requirement | Purpose | Notes |
|---|---|---|
| Python ≥ 3.10 | Runtime | `python --version` |
| [Ollama](https://ollama.com) | Local worker LLM | `ollama serve` must be running |
| Worker model pulled | The LLM that writes code | e.g. `ollama pull llama3.1:70b` |
| OpenRouter API key | Orchestrator (DeepSeek free tier) | [openrouter.ai](https://openrouter.ai) — free |
| `pyyaml` + `python-dotenv` | Config loading | Installed with the runtime |
| Git repo | Auto-commit after each task | `git init` if needed |

> **No GPU required for the orchestrator** — DeepSeek runs on OpenRouter's servers for free. The worker runs locally via Ollama — any model works, larger is better.

---

## Installation

### Claude Code

```bash
claude plugin install github:Le-Xuan-Thang/workflow-kit
```

Skills available after restart:
```
/workflow-kit:workflow-init
/workflow-kit:workflow-plan
/workflow-kit:workflow-start
/workflow-kit:workflow-status
/workflow-kit:workflow-monitor
```

### Codex CLI

Add to `~/.codex/config.toml`:
```toml
[plugins."workflow-kit"]
source = "github:Le-Xuan-Thang/workflow-kit"
enabled = true

# Required for background dispatcher subagents:
[features]
multi_agent = true
```

Skills callable as:
```
$workflow-kit:workflow-init
$workflow-kit:workflow-plan
$workflow-kit:workflow-start
$workflow-kit:workflow-status
$workflow-kit:workflow-monitor
```

### OpenCode

```bash
opencode plugin install github:Le-Xuan-Thang/workflow-kit
```

### Gemini CLI

Add to `~/.gemini/config.yaml`:
```yaml
plugins:
  - source: github:Le-Xuan-Thang/workflow-kit
    name: workflow-kit
```

Skills callable via `activate_skill workflow-kit:workflow-init` or however your Gemini CLI version triggers skills.

### Standalone CLI (no AI tool needed)

```bash
git clone https://github.com/Le-Xuan-Thang/workflow-kit.git
cd workflow-kit
pip install pyyaml python-dotenv
# or: uv add pyyaml python-dotenv

# Run directly:
python -m workflow_kit benchmark
python -m workflow_kit plan
python -m workflow_kit start
python -m workflow_kit status
python -m workflow_kit stop
```

---

## Quick Start (5 steps)

### 1. Install dependencies

```bash
pip install pyyaml python-dotenv
# or via uv:
uv add pyyaml python-dotenv
```

### 2. Pull a worker model

```bash
ollama pull llama3.1:70b     # recommended — strong code quality
# lighter alternatives:
ollama pull qwen2.5-coder:32b
ollama pull deepseek-coder-v2:16b
ollama pull llama3.1:8b      # fast but weaker on complex edits
```

### 3. Set your API key

```bash
export OPENROUTER_API_KEY=sk-or-...
# or put it in .env:
echo "OPENROUTER_API_KEY=sk-or-..." >> .env
```

### 4. Initialize

```
/workflow-kit:workflow-init
```

Follow the prompts. Accepts defaults for everything — just press Enter.  
At the end it runs a ~3 minute benchmark and prints your worker's capability scores.

### 5. Write goals, plan, start

Edit `goals.md`:
```markdown
# Project Goals

- Add a dark mode toggle that persists to localStorage
- Write unit tests for the CSV export endpoint
- Refactor the auth middleware to use the new session format
```

Then:
```
/workflow-kit:workflow-plan
/workflow-kit:workflow-start
```

The dispatcher runs in the background. Check progress anytime:
```
/workflow-kit:workflow-status
```

---

## Configuration — `workflow.yaml`

Created automatically by `/workflow-kit:workflow-init`. Edit as needed.

### Minimal config

```yaml
project:
  name: "my-project"
  description: "One-line description"
  root: "."

orchestrator:
  endpoint: "https://openrouter.ai/api/v1/chat/completions"
  api_key: "${OPENROUTER_API_KEY}"
  model: "deepseek/deepseek-chat:free"

worker:
  endpoint: "http://localhost:11434/v1/chat/completions"
  api_key: "ollama"
  model: "llama3.1:70b"

settings:
  work_hours: "9-21"
  auto_commit: true
  verify_syntax: true
  max_retries: 2
  dashboard_port: 7860
```

### Multi-model fallback chain

If the primary model is unavailable, the runtime tries each fallback in order:

```yaml
# Workers: try 70b first, fall back to 32b, then 8b
workers:
  - endpoint: "http://localhost:11434/v1/chat/completions"
    api_key: "ollama"
    model: "llama3.1:70b"
  - endpoint: "http://localhost:11434/v1/chat/completions"
    api_key: "ollama"
    model: "qwen2.5-coder:32b"
  - endpoint: "http://localhost:11434/v1/chat/completions"
    api_key: "ollama"
    model: "llama3.1:8b"

# Orchestrators: DeepSeek free, fall back to paid if rate-limited
orchestrators:
  - endpoint: "https://openrouter.ai/api/v1/chat/completions"
    api_key: "${OPENROUTER_API_KEY}"
    model: "deepseek/deepseek-chat:free"
  - endpoint: "https://openrouter.ai/api/v1/chat/completions"
    api_key: "${OPENROUTER_API_KEY}"
    model: "deepseek/deepseek-chat"
```

### Settings reference

| Key | Default | Description |
|---|---|---|
| `work_hours` | `"9-21"` | Only dispatch tasks during these hours (24h local time). `"0-24"` = always. |
| `auto_commit` | `true` | Git commit after each successful task |
| `verify_syntax` | `true` | Run `compile()` (Python) or `node --check` (JS) before accepting output |
| `max_retries` | `2` | Retry failed tasks N times with error feedback before skipping |
| `dashboard_port` | `7860` | Port for the web dashboard |

### Environment variables

`workflow.yaml` values can reference environment variables using `${VAR_NAME}`. The runtime loads `.env` automatically via `python-dotenv`.

```bash
# .env
OPENROUTER_API_KEY=sk-or-v1-...
AI_API_KEY=sk-or-v1-...   # alias — also recognized
```

---

## Skills Reference

### `/workflow-kit:workflow-init`

**When to use:** First time setting up workflow-kit in a project.

What it does:
1. Detects project root (walks up to find `.git`, `pyproject.toml`, or `package.json`)
2. Asks for orchestrator + worker model/endpoint/key (all have defaults)
3. Writes `workflow.yaml` and a template `goals.md`
4. Creates `.workflow/tasks/{pending,active,completed}/` and `.workflow/memory/`
5. Adds `.workflow/` and `workflow.yaml` to `.gitignore`
6. **Runs benchmark** — profiles worker across 7 skill areas, writes `.workflow/worker_capability.json`

Re-benchmark only (skip setup):
```
/workflow-kit:workflow-init --rebenchmark
# or:
python -m workflow_kit benchmark
```

---

### `/workflow-kit:workflow-plan`

**When to use:** After editing `goals.md`, or when the pending task queue is empty.

What it does:
1. Reads `goals.md` + completed task history + worker capability profile
2. Calls DeepSeek to plan 3–5 tasks matched to worker capability
3. Decomposes any task requiring a skill score < 3.0 into smaller sub-tasks
4. Writes task JSONs to `.workflow/tasks/pending/`

Plan more tasks at once:
```bash
python -m workflow_kit plan -n 10
```

---

### `/workflow-kit:workflow-start`

**When to use:** When you want to start (or restart) the automated loop.

What it does:
1. Verifies `workflow.yaml`, `goals.md`, and at least one pending task exist
2. Checks if dispatcher is already running (reads `.workflow/dispatcher.pid`)
3. Starts `python -m workflow_kit start` as a background process
4. Writes PID to `.workflow/dispatcher.pid`

Stop the dispatcher:
```
/workflow-kit:workflow-start --stop
# or:
python -m workflow_kit stop
```

---

### `/workflow-kit:workflow-status`

**When to use:** Quick inline check without opening a dashboard.

Example output:
```
── Workflow Status ──────────────────────────────────────
  Active:    feat-003-dark-mode (started 4 min ago)
  Pending:   2 tasks
  Completed: 7 tasks (6 ok, 1 failed)
  Workers:   llama3.1:70b → qwen2.5-coder:32b
  Orch:      deepseek/deepseek-chat:free
  Benchmarked worker: llama3.1:70b (overall 3.4/5)

  Last completed:
    feat-002: Built CSV export endpoint
    feat-001: Added dark mode toggle
─────────────────────────────────────────────────────────
```

---

### `/workflow-kit:workflow-monitor`

**When to use:** Live progress tracking.

Two modes:

**TUI** (default — terminal required):
```bash
python -m workflow_kit monitor
```
Rich dashboard with task queue, live log, and command bar (`/pause`, `/resume`, `/skip <id>`, `/retry <id>`, `/quit`).

**Web dashboard**:
```bash
python -m workflow_kit dashboard
# open http://localhost:7860
```
Browser dashboard with task cards, live log stream (SSE), goals viewer, pause/resume buttons.

> In Codex App or sandboxed environments where terminal control is blocked, use the web dashboard or `/workflow-kit:workflow-status` for inline checks.

---

## Overnight Scheduling

Let the dispatcher run while you sleep and read a summary in the morning.

```bash
# Run tonight 21:00 → 09:00, generate report at stop
python -m workflow_kit schedule --start 21:00 --stop 09:00

# Recurring every night
python -m workflow_kit schedule --start 21:00 --stop 09:00 --recurring

# View current schedule
python -m workflow_kit schedule

# Remove
python -m workflow_kit schedule --remove
```

Stop with morning report:
```bash
python -m workflow_kit stop --report
# Prints report and saves to .workflow/reports/YYYY-MM-DD.md
```

---

## State Layout

Created by `/workflow-kit:workflow-init`, **never committed** (gitignored):

```
your-project/
├── workflow.yaml                    ← config (gitignore if API keys are inline)
├── goals.md                         ← your high-level goals (safe to commit)
└── .workflow/
    ├── dispatcher.pid               ← PID of running dispatcher
    ├── current.json                 ← active task + last status snapshot
    ├── worker_capability.json       ← benchmark results + skill scores
    ├── tasks/
    │   ├── pending/                 ← task JSONs waiting to run
    │   ├── active/                  ← task currently executing
    │   └── completed/               ← finished tasks (success + failed)
    ├── memory/
    │   ├── decisions.md             ← append-only log of decisions made
    │   └── progress.md              ← progress snapshots
    └── reports/                     ← morning reports (YYYY-MM-DD.md)
```

---

## Worker Capability Scores

The benchmark runs 7 skill challenge sets against your worker model and scores 0–5:

| Skill | What it measures |
|---|---|
| `code_gen` | Writing new functions/classes from a description |
| `code_edit` | Modifying existing code accurately |
| `bug_fix` | Identifying and fixing broken code |
| `frontend_js` | JavaScript / DOM manipulation |
| `css_styling` | CSS rules and layout |
| `api_design` | REST endpoint structure and request/response shapes |
| `refactor` | Extracting, renaming, restructuring code |

The orchestrator uses these scores to match task complexity to what the worker can actually do — it won't assign a bug-fix task to a model with `bug_fix: 2.1`.

Example profile output:
```
Capability profile for llama3.1:70b:
  code_gen        ████████░░  4.2/5
  code_edit       ███████░░░  3.8/5
  bug_fix         █████░░░░░  2.9/5
  frontend_js     ███████░░░  3.5/5
  css_styling     ████████░░  4.0/5
  api_design      ██████░░░░  3.2/5
  refactor        █████░░░░░  2.5/5

Overall: 3.4/5

Summary: Strong at generating new code and CSS. Moderate JS and API work.
Weak at bug fixes and refactoring — decompose these into smaller edits.
```

---

## Platform Compatibility

| Feature | Claude Code | Codex CLI | Codex App | OpenCode | Gemini CLI | Standalone |
|---|---|---|---|---|---|---|
| All 5 skills | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `python -m workflow_kit` CLI | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Background dispatcher | ✅ | ✅ | ⚠️ use web dashboard | ✅ | ✅ | ✅ |
| TUI monitor | ✅ | ✅ | ❌ sandboxed | ✅ | ✅ | ✅ |
| Web dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Git auto-commit | ✅ | ✅ | ⚠️ use App UI | ✅ | ✅ | ✅ |
| Multi-agent subagents | ✅ | ✅ `multi_agent=true` | ✅ | ✅ | ✅ | — |
| Overnight schedule | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |

**Codex App notes:** The App sandbox blocks `git checkout -b`, `git push`, and network outside the task. The dispatcher still runs and commits — use the App's native "Create branch" button to push when done.

---

## Troubleshooting

### `ConfigError: workflow.yaml not found`
Run `/workflow-kit:workflow-init` first. Make sure you're running commands from the project root.

### `ConfigError: Environment variable 'OPENROUTER_API_KEY' not set`
```bash
export OPENROUTER_API_KEY=sk-or-...
# or add to .env in your project root
```

### Worker benchmark times out
Ollama isn't running or the model isn't pulled:
```bash
ollama serve          # start Ollama
ollama pull llama3.1:70b  # pull model
```

### Tasks keep failing
Check `.workflow/tasks/completed/` for failed task JSONs — they contain the error and the worker's raw output. If failure rate > 30%, re-benchmark:
```bash
python -m workflow_kit benchmark
```
Consider switching to a more capable model or using the fallback chain.

### Dispatcher exits immediately
Check `.workflow/` exists and has at least one file in `pending/`. Run `/workflow-kit:workflow-plan` first.

### `pyyaml` or `python-dotenv` not found
```bash
pip install pyyaml python-dotenv
# or:
uv add pyyaml python-dotenv
```

---

## License

MIT — see [LICENSE](LICENSE).
