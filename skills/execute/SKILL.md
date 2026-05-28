---
name: execute
description: Use to start the dispatcher loop — every task is executed by a worker agent then validated by a domain-expert reviewer agent before being marked done. Requires at least one pending task. Also triggers when the user says "start building", "run the dispatcher", "execute the workplan", or "start the dev loop". Pass --stop to stop a running dispatcher.
argument-hint: "[--stop]"
allowed-tools: Read, Bash
---

# Workflow Execute

Start the dispatcher. For every task: worker builds → reviewer validates → PASS marks done, FAIL retries, max retries exceeded escalates to user.

## Step 1: Check prerequisites

```bash
python3 -c "
from workflow_kit.runtime.state import load_state
from pathlib import Path
s = load_state(Path('.'))
print('phase:', s.phase)
" && \
ls workflow/tasks/pending/*.json 2>/dev/null | wc -l | xargs -I{} echo "pending tasks: {}"
```

- Phase not `plan` or `execute`: warn with correct next skill.
- 0 pending tasks: "Run /workflow-kit:plan first."

## Step 2: Handle --stop

If user passes `--stop` or says "stop":
```bash
python -m workflow_kit stop
```
Done.

## Step 3: Check if already running

```bash
cat workflow/dispatcher.pid 2>/dev/null | xargs -I{} kill -0 {} 2>/dev/null && echo "running" || echo "stopped"
```
If running: "Dispatcher already running. Use /workflow-kit:status."

## Step 4: Advance state to 'execute'

```python
from workflow_kit.runtime.state import load_state, save_state
from pathlib import Path
s = load_state(Path('.'))
if s.phase == "plan":
    s.transition_to("execute")
    save_state(s, Path('.'))
    print("Phase: plan → execute")
```

## Step 5: Start dispatcher

```bash
python -m workflow_kit execute &
echo $! > workflow/dispatcher.pid
```

## Step 6: Report

```
✓ Dispatcher started (PID N)

  Loop: worker builds → reviewer validates → PASS/FAIL
  Max retries: <from workflow.yaml>

  Monitor:
    /workflow-kit:status   — inline progress
    /workflow-kit:monitor  — live dashboard

  When all tasks complete:
    /workflow-kit:synthesize  — package and review deliverables
```

## Reviewer escalation

When a task fails review max_retries times, the dispatcher pauses and prints:

```
⚠ Task <id> failed review N times
  Reviewer (<domain>): <feedback summary>

  A) Skip this task
  B) Retry with your guidance (describe what to fix)
  C) Redesign the task entirely
```

Respond inline — dispatcher waits before continuing.
