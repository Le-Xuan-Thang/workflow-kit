"""Per-task metrics recording. Append-only JSONL at .workflow/metrics.jsonl."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class TaskMetrics:
    task_id: str
    feature_name: str
    status: str                      # "completed" | "failed" | "escalated"
    started_at: str                  # ISO timestamp
    completed_at: str                # ISO timestamp
    duration_seconds: float
    worker_model: str
    retry_count: int = 0
    reviewer_model: Optional[str] = None
    reviewer_domain: Optional[str] = None
    reviewer_passed: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TaskMetrics":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def record_metric(metric: TaskMetrics, project_root: Path):
    """Append one metric record to .workflow/metrics.jsonl."""
    path = project_root / ".workflow" / "metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(metric.to_dict(), ensure_ascii=False) + "\n")


def load_metrics(project_root: Path, limit: int = 100) -> list[TaskMetrics]:
    """Load last `limit` metric records from .workflow/metrics.jsonl."""
    path = project_root / ".workflow" / "metrics.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    records = []
    for line in lines[-limit:]:
        try:
            records.append(TaskMetrics.from_dict(json.loads(line)))
        except Exception:
            pass
    return records


def summarize(metrics: list[TaskMetrics]) -> dict:
    """Compute summary stats from a list of TaskMetrics."""
    if not metrics:
        return {}
    total = len(metrics)
    completed = sum(1 for m in metrics if m.status == "completed")
    failed = sum(1 for m in metrics if m.status == "failed")
    escalated = sum(1 for m in metrics if m.status == "escalated")
    avg_duration = sum(m.duration_seconds for m in metrics) / total
    reviewer_metrics = [m for m in metrics if m.reviewer_passed is not None]
    reviewer_pass_rate = (
        sum(1 for m in reviewer_metrics if m.reviewer_passed) / len(reviewer_metrics)
        if reviewer_metrics else None
    )
    avg_retries = sum(m.retry_count for m in metrics) / total
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "escalated": escalated,
        "pass_rate": round(completed / total * 100, 1),
        "avg_duration_seconds": round(avg_duration, 1),
        "avg_retries": round(avg_retries, 2),
        "reviewer_pass_rate": round(reviewer_pass_rate * 100, 1) if reviewer_pass_rate is not None else None,
    }
