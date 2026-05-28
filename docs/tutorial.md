# workflow-kit — Complete Tutorial

A practical guide from zero to a running AI product lifecycle.
Estimated time: 30–60 minutes.

---

## Prerequisites

- Claude Code installed (`claude --version`)
- Python 3.9+ (`python3 --version`)
- Git (`git --version`)
- At least one LLM available:
  - **Local:** Ollama (`ollama --version`) with a model pulled
  - **Cloud:** API key for OpenRouter, Anthropic, or OpenAI

---

## Part 1: Installation

### Step 1: Add the marketplace

```bash
claude plugin marketplace add Le-Xuan-Thang/workflow-kit
```

Expected output:
```
Adding marketplace…
✔ Successfully added marketplace: Le-Xuan-Thang
```

### Step 2: Install the plugin

```bash
claude plugin install workflow-kit
```

Expected output:
```
Installing plugin "workflow-kit"...
✔ Successfully installed plugin: workflow-kit@Le-Xuan-Thang (scope: user)
```

### Step 3: Install Python runtime

```bash
pip install pyyaml python-dotenv
```

### Step 4: Restart Claude Code

The skills are now available: `/workflow-kit:init`, `/workflow-kit:plan`, etc.

---

### Installing on other platforms

<details>
<summary><strong>Codex CLI</strong></summary>

```bash
# Step 1: add the marketplace
codex plugin marketplace add Le-Xuan-Thang/workflow-kit

# Step 2: install the plugin
codex plugin add workflow-kit@Le-Xuan-Thang
```

Verify:
```
codex plugin list
# workflow-kit@Le-Xuan-Thang  installed, enabled  0.2.0
```

Skills are available in Codex sessions as `$workflow-kit:init`, etc.

</details>

<details>
<summary><strong>OpenCode</strong></summary>

```bash
opencode plugin github:Le-Xuan-Thang/workflow-kit
```

This copies all 7 skills to `~/.config/opencode/skills/` automatically.

</details>

<details>
<summary><strong>Gemini CLI</strong></summary>

Add to `~/.gemini/config.yaml`:

```yaml
plugins:
  - source: github:Le-Xuan-Thang/workflow-kit
    name: workflow-kit
```

> Note: Not tested on this machine. Command format may vary by Gemini CLI version.

</details>

<details>
<summary><strong>Standalone CLI (no AI tool)</strong></summary>

```bash
git clone https://github.com/Le-Xuan-Thang/workflow-kit.git
cd workflow-kit
pip install pyyaml python-dotenv
pip install -e .
python -m workflow_kit --help
```

</details>

---

## Part 2: Initialize a project

Navigate to your project directory:

```bash
cd ~/my-project
```

### Step 5: Run the init wizard

```
/workflow-kit:init
```

The wizard runs in phases. Here is what to expect:

**Phase 1 — Environment scan:**
```
Environment:
  Python     ✓ 3.11.4
  Runtime    ✓ installed
  Ollama     ✓ running (models: llama3.1:8b, qwen2.5-coder:7b)
  RAM        32 GB
  OpenRouter ✗ missing
  Git        ✓ git version 2.43.0
```

**Phase 2 — Vision:**
> "Let's define your product. **Vision** first — what is this product's long-term direction?"

Example answer:
> "A Python library for parsing and transforming scientific data from HDF5 files, used by research teams worldwide."

**Phase 3 — Mission:**
> "**Mission** — who does this product serve, and what urgent problem does it solve?"

Example answer:
> "Research teams who need to convert HDF5 sensor data into clean pandas DataFrames without writing boilerplate parsing code."

**Phase 4 — Core (system scan + your input):**
The wizard scans your system automatically, then asks:
- Timeline and team size?
- Main competitors?
- Hard constraints?

**Phase 5 — Product type detection:**
```
I detected this as a library project. Correct? (y/n)
```

**Phase 6 — LLM setup:**
Choose from:
- A) Local (Ollama) — private, free
- B) Cloud (OpenRouter/OpenAI/Anthropic)
- C) Hybrid — local worker + free DeepSeek orchestrator (recommended)

For this tutorial, choose **C (Hybrid)**:
- Worker: your local Ollama model (e.g. `llama3.1:8b`)
- Orchestrator: DeepSeek via OpenRouter (free tier)

**Phase 7 — Reviewer LLM setup (new in v0.3):**
> "Do you want a reviewer LLM — a separate model that validates each worker output?"

Choose **A: Yes — cloud reviewer + local worker**:
```yaml
reviewers:
  - endpoint: "https://api.anthropic.com/v1/messages"
    api_key: "${ANTHROPIC_API_KEY}"
    model: "claude-haiku-4-5-20251001"
```

**Result — files created:**
```
✔ workflow/product.md         (your Vision/Mission/Core)
✔ workflow/state.yaml         (phase: define)
✔ workflow/reviewers/         (code-reviewer.md, editor.md)
✔ workflow.yaml               (your config)
```

---

## Part 3: Configure `workflow.yaml`

The init wizard creates `workflow.yaml`. Here is a complete annotated example:

```yaml
project:
  name: "hdf5-toolkit"
  description: "Parse HDF5 sensor data into pandas DataFrames"
  root: "."

# Orchestrator: plans tasks (cloud recommended — uses free DeepSeek tier)
orchestrator:
  endpoint: "https://openrouter.ai/api/v1/chat/completions"
  api_key: "${OPENROUTER_API_KEY}"
  model: "deepseek/deepseek-chat:free"

# Worker: builds the code (local Ollama for privacy + zero cost)
worker:
  endpoint: "http://localhost:11434/v1/chat/completions"
  api_key: "ollama"
  model: "llama3.1:8b"

# Reviewer: validates worker output (cross-provider = less sycophancy bias)
reviewers:
  - endpoint: "https://api.anthropic.com/v1/messages"
    api_key: "${ANTHROPIC_API_KEY}"
    model: "claude-haiku-4-5-20251001"

settings:
  work_hours: "9-21"         # only dispatch tasks between 9am–9pm
  auto_commit: true          # git commit after each successful task
  verify_syntax: true        # syntax check before accepting worker output
  max_retries: 2             # reviewer FAIL retries before escalating to user
  max_parallel_tasks: 2      # run up to 2 tasks concurrently (new in v0.3)
  dashboard_port: 7860       # web dashboard port
```

### Multi-model fallback (optional)

If your primary worker model fails, workflow-kit falls back automatically:

```yaml
workers:
  - endpoint: "http://localhost:11434/v1/chat/completions"
    api_key: "ollama"
    model: "llama3.1:70b"       # primary (needs 48GB RAM)
  - endpoint: "http://localhost:11434/v1/chat/completions"
    api_key: "ollama"
    model: "llama3.1:8b"        # fallback if 70b unavailable
```

---

## Part 4: Generate a workplan

### Step 6: Run `/workflow-kit:plan`

```
/workflow-kit:plan
```

The orchestrator reads your `workflow/product.md` and generates a structured workplan. Example output for the HDF5 library:

```
[orchestrator] Planning 3 tasks (primary: deepseek/deepseek-chat:free)...
[orchestrator] Queued: feat-001 — HDF5 file reader with context manager
[orchestrator] Queued: feat-002 — Sensor data parser with dtype mapping
[orchestrator] Queued: feat-003 — DataFrame export with unit preservation
```

Review `workflow/workplan.md` before executing. You can edit task descriptions, add tasks, or remove tasks you do not want.

---

## Part 5: Execute

### Step 7: Start the dispatcher

```
/workflow-kit:execute
```

Or from the terminal:
```bash
python -m workflow_kit start
```

The dispatcher runs this loop for each task:

```
1. Pick task from workflow/tasks/pending/
2. Write recovery snapshot → .workflow/recovery/<task_id>.json
3. Call worker LLM with task spec
4. Apply surgical edits to files
5. Syntax check (Python/JS)
6. Call reviewer LLM → PASS or FAIL
   - FAIL: append feedback, retry worker (up to max_retries)
   - After max_retries: escalate to you
7. Git commit
8. Record metrics → .workflow/metrics.jsonl
9. Repeat
```

**Example session output:**

```
[dispatcher] Recovering 0 interrupted tasks...
[dispatcher] Watching (max_parallel_tasks=2) ...

==================================================
Executing: HDF5 file reader with context manager (feat-001)
==================================================
[worker] Calling llama3.1:8b (primary)...
  Applied surgical edit to src/reader.py
  Syntax check: ✓
[reviewer] PASS (code-reviewer/claude-haiku-4-5-20251001): Clean implementation,
  proper context manager protocol, error handling looks good.
  ✅ feat-001 COMPLETED

==================================================
Executing: Sensor data parser with dtype mapping (feat-002)
==================================================
[worker] Calling llama3.1:8b (primary)...
  Applied surgical edit to src/parser.py
  Syntax check: ✓
[reviewer] FAIL (code-reviewer/claude-haiku-4-5-20251001): Missing handling for
  float16 dtype. The dtype_map on line 23 only covers int32, int64, float32, float64.
  Retrying (attempt 1/2)...
[worker] Calling llama3.1:8b (primary)...
  Applied surgical edit to src/parser.py
  Syntax check: ✓
[reviewer] PASS: float16 added correctly, all dtypes covered.
  ✅ feat-002 COMPLETED
```

### Check status anytime

```
/workflow-kit:status
```

Example output:
```
Phase:       execute
Active task: feat-003 (running)
Pending:     0
Completed:   2 (✓ feat-001, ✓ feat-002)

┌─────────────────────────────────────────┐
│           Task Metrics (last 50)        │
├─────────────────────────────────────────┤
│ Total tasks:         2                  │
│ Completed:           2  (100.0%)        │
│ Failed:              0                  │
│ Escalated:           0                  │
│ Avg duration:      45.3s               │
│ Avg retries:        0.50               │
│ Reviewer pass:     75.0%               │
└─────────────────────────────────────────┘
```

---

## Part 6: Crash recovery (new in v0.3)

If the dispatcher crashes mid-task (power loss, OOM, Ctrl+C during a task), workflow-kit recovers automatically on next startup:

```bash
# Simulate crash during feat-003:
python -m workflow_kit start
# → Ctrl+C mid-task (or kill -9)

# Restart:
python -m workflow_kit start
```

Output:
```
[dispatcher] Recovering 1 interrupted task(s)...
[dispatcher]   Rolled back files for: feat-003 (src/exporter.py restored)
[dispatcher]   Re-queued for retry: feat-003
[dispatcher] Watching (max_parallel_tasks=2) ...
```

The interrupted task restarts from scratch with original files intact. No manual intervention needed.

**Graceful Ctrl+C:**

```bash
python -m workflow_kit start
# → Ctrl+C (during a task)
```
Output:
```
[dispatcher] Shutdown requested — finishing current task...
[dispatcher] Stopped cleanly.
```
The current task always completes before stopping.

---

## Part 7: Parallel execution (new in v0.3)

With `max_parallel_tasks: 2`, independent tasks run concurrently:

```
Executing: feat-003 — DataFrame export (thread-1)
Executing: feat-004 — CLI entry point (thread-2)
```

**File conflict safety:** if two tasks modify the same file, the second waits automatically:

```
feat-005 (modifies src/reader.py) → WAITING
  (feat-001 is currently modifying src/reader.py)
feat-005 dispatched after feat-001 completes
```

No configuration needed — conflict detection is automatic.

---

## Part 8: Overnight scheduling

Let the dispatcher work while you sleep:

```bash
# Tonight 21:00 → stop at 09:00, generate morning report
python -m workflow_kit schedule --start 21:00 --stop 09:00

# Every night (recurring)
python -m workflow_kit schedule --start 21:00 --stop 09:00 --recurring

# Morning: read the report
cat workflow/output/reports/$(date +%Y-%m-%d).md
```

---

## Part 9: Synthesize deliverables

When all tasks complete:

```
/workflow-kit:synthesize
```

Packages deliverables based on your product type:

| Product type | Deliverables |
|---|---|
| `library` | Package tarball, API docs, CHANGELOG |
| `webapp` | Code repo, deployed URL, user guide |
| `paper` | PDF/MD document, bibliography |
| `api` | OpenAPI spec, Postman collection |
| `dataset` | Data files, data card, methodology |

You can:
- **Approve** → moves to `maintain` phase
- **Give feedback** → creates sub-tasks, loops back to execute
- **Reject specific items** → targeted rework

---

## Part 10: Maintain

```
/workflow-kit:maintain
```

Sets up scheduled jobs for your product type:

| Product type | Auto-created jobs |
|---|---|
| `library` | CVE scan, compatibility check |
| `webapp` | Dependency audit, uptime check |
| `paper` | Citation freshness, related-work scan |
| `api` | Health check, schema drift detection |

---

## Troubleshooting

### "workflow/product.md not found"
Run `/workflow-kit:init` first from the project root.

### "worker_capability.json not found"
Run `/workflow-kit:init` or `python -m workflow_kit benchmark` to profile your worker.

### Reviewer keeps failing tasks
Check completed task JSONs for exact feedback:
```bash
cat workflow/tasks/completed/feat-*.json | python3 -c "
import sys, json
for line in sys.stdin:
    t = json.loads(line) if line.strip().startswith('{') else None
    if t and t.get('error'): print(t['task_id'], '→', t['error'][:100])
"
```
Options:
- Edit `workflow/reviewers/code-reviewer.md` to adjust review criteria
- Lower `max_retries` in `workflow.yaml` to escalate sooner
- After escalation: choose "Retry with your guidance"

### Ollama not running
```bash
ollama serve
ollama pull llama3.1:8b  # or your chosen model
```

### Phase mismatch ("phase is X, expected Y")
```bash
cat workflow/state.yaml  # check current phase
# Use the correct skill for your phase, or pass --reset to start over
```

### Metrics not showing in /status
Run at least one task first. Metrics are stored in `.workflow/metrics.jsonl`.

---

## Full CLI reference

```bash
python -m workflow_kit benchmark          # profile worker model capability
python -m workflow_kit workplan           # generate tasks from workflow/product.md
python -m workflow_kit start              # start dispatcher (auto-recovers on crash)
python -m workflow_kit start --resume     # same, explicit flag
python -m workflow_kit status             # print lifecycle status + metrics
python -m workflow_kit stop               # graceful stop (finishes current task)
python -m workflow_kit stop --report      # stop + generate morning report
python -m workflow_kit schedule \
  --start 21:00 --stop 09:00 --recurring  # overnight cron
```

---

## Environment variables

| Variable | Used for |
|---|---|
| `OPENROUTER_API_KEY` | Orchestrator (DeepSeek free tier) |
| `ANTHROPIC_API_KEY` | Reviewer (Claude Haiku) |
| `OPENAI_API_KEY` | Alternative reviewer/worker |

Store in `.env` at project root (auto-loaded by workflow-kit):
```bash
echo "OPENROUTER_API_KEY=sk-or-..." >> .env
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
echo ".env" >> .gitignore  # never commit keys
```

---

*workflow-kit v0.3 — [GitHub](https://github.com/Le-Xuan-Thang/workflow-kit)*
