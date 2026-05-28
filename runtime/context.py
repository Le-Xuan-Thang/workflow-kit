"""All .workflow/ I/O — tasks, memory, current state. No LLM calls here."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class TaskSpec:
    task_id: str
    type: str
    feature_name: str
    description: str
    files_to_modify: list[str]
    context_files: list[str]
    instructions: list[str]
    status: str = "pending"
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, d: dict) -> "TaskSpec":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


class WorkflowContext:
    def __init__(self, project_root: Path):
        self.root = Path(project_root)
        self.wf = self.root / ".workflow"
        self.pending = self.wf / "tasks" / "pending"
        self.active = self.wf / "tasks" / "active"
        self.completed = self.wf / "tasks" / "completed"
        self.memory = self.wf / "memory"

    def ensure_dirs(self):
        for d in [self.pending, self.active, self.completed, self.memory]:
            d.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str, bucket: str) -> Path:
        return getattr(self, bucket) / f"{task_id}.json"

    def write_task(self, task: TaskSpec, bucket: str):
        path = self._task_path(task.task_id, bucket)
        path.write_text(json.dumps(task.to_dict(), indent=2, ensure_ascii=False))

    def read_task(self, task_id: str, bucket: str) -> Optional[TaskSpec]:
        path = self._task_path(task_id, bucket)
        if not path.exists():
            return None
        return TaskSpec.from_dict(json.loads(path.read_text()))

    def move_task(self, task_id: str, from_bucket: str, to_bucket: str):
        src = self._task_path(task_id, from_bucket)
        dst = self._task_path(task_id, to_bucket)
        if src.exists():
            shutil.move(str(src), str(dst))

    def get_next_pending(self) -> Optional[TaskSpec]:
        tasks = sorted(self.pending.glob("*.json"))
        if not tasks:
            return None
        return TaskSpec.from_dict(json.loads(tasks[0].read_text()))

    def pending_count(self) -> int:
        return len(list(self.pending.glob("*.json")))

    def completed_task_summaries(self, limit: int = 10) -> list[str]:
        tasks = sorted(
            self.completed.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        summaries = []
        for t in tasks[:limit]:
            data = json.loads(t.read_text())
            status = "✓" if not data.get("error") else "✗"
            summaries.append(f"{status} {data.get('feature_name', data['task_id'])}")
        return summaries

    def save_current(self, **kwargs):
        path = self.wf / "current.json"
        current = {}
        if path.exists():
            current = json.loads(path.read_text())
        current.update(kwargs)
        current["last_updated"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(current, indent=2, ensure_ascii=False))

    def load_current(self) -> dict:
        path = self.wf / "current.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def append_decision(self, decision: str):
        path = self.memory / "decisions.md"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(path, "a") as f:
            f.write(f"\n## {ts}\n- {decision}\n")

    def capability_path(self) -> Path:
        return self.wf / "worker_capability.json"

    def load_capability(self) -> Optional[dict]:
        p = self.capability_path()
        if not p.exists():
            return None
        return json.loads(p.read_text())

    def save_capability(self, profile: dict):
        self.capability_path().write_text(
            json.dumps(profile, indent=2, ensure_ascii=False)
        )
