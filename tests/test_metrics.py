"""Tests for workflow_kit.runtime.metrics."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from workflow_kit.runtime.metrics import (
    TaskMetrics,
    record_metric,
    load_metrics,
    summarize,
)


def _make_metric(**kwargs) -> TaskMetrics:
    defaults = dict(
        task_id="feat-001",
        feature_name="Test Feature",
        status="completed",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:01:00+00:00",
        duration_seconds=60.0,
        worker_model="llama3.1:8b",
        retry_count=0,
        reviewer_model=None,
        reviewer_domain=None,
        reviewer_passed=None,
    )
    defaults.update(kwargs)
    return TaskMetrics(**defaults)


# ── record_metric ────────────────────────────────────────────────────────────


def test_record_metric_creates_file(tmp_path):
    metric = _make_metric()
    record_metric(metric, tmp_path)
    path = tmp_path / ".workflow" / "metrics.jsonl"
    assert path.exists()


def test_record_metric_appends(tmp_path):
    m1 = _make_metric(task_id="feat-001")
    m2 = _make_metric(task_id="feat-002")
    record_metric(m1, tmp_path)
    record_metric(m2, tmp_path)
    path = tmp_path / ".workflow" / "metrics.jsonl"
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["task_id"] == "feat-001"
    assert json.loads(lines[1])["task_id"] == "feat-002"


# ── load_metrics ─────────────────────────────────────────────────────────────


def test_load_metrics_empty_when_no_file(tmp_path):
    result = load_metrics(tmp_path)
    assert result == []


def test_load_metrics_parses_records(tmp_path):
    metric = _make_metric(task_id="feat-001", status="completed")
    record_metric(metric, tmp_path)
    records = load_metrics(tmp_path)
    assert len(records) == 1
    assert records[0].task_id == "feat-001"
    assert records[0].status == "completed"
    assert records[0].duration_seconds == 60.0


def test_load_metrics_respects_limit(tmp_path):
    for i in range(10):
        record_metric(_make_metric(task_id=f"feat-{i:03d}"), tmp_path)
    records = load_metrics(tmp_path, limit=3)
    assert len(records) == 3
    # Should be the last 3 records
    assert records[-1].task_id == "feat-009"
    assert records[0].task_id == "feat-007"


# ── summarize ────────────────────────────────────────────────────────────────


def test_summarize_empty_returns_empty_dict():
    result = summarize([])
    assert result == {}


def test_summarize_computes_pass_rate():
    metrics = [
        _make_metric(task_id="feat-001", status="completed", duration_seconds=10.0),
        _make_metric(task_id="feat-002", status="completed", duration_seconds=20.0),
        _make_metric(task_id="feat-003", status="failed", duration_seconds=5.0),
    ]
    stats = summarize(metrics)
    assert stats["total"] == 3
    assert stats["completed"] == 2
    assert stats["failed"] == 1
    assert stats["escalated"] == 0
    assert stats["pass_rate"] == round(2 / 3 * 100, 1)
    assert stats["avg_duration_seconds"] == round((10.0 + 20.0 + 5.0) / 3, 1)


def test_summarize_reviewer_pass_rate():
    metrics = [
        _make_metric(
            task_id="feat-001", status="completed",
            reviewer_model="claude-sonnet-4-6",
            reviewer_domain="code-reviewer",
            reviewer_passed=True,
        ),
        _make_metric(
            task_id="feat-002", status="completed",
            reviewer_model="claude-sonnet-4-6",
            reviewer_domain="code-reviewer",
            reviewer_passed=True,
        ),
        _make_metric(
            task_id="feat-003", status="failed",
            reviewer_model="claude-sonnet-4-6",
            reviewer_domain="code-reviewer",
            reviewer_passed=False,
        ),
    ]
    stats = summarize(metrics)
    assert stats["reviewer_pass_rate"] == round(2 / 3 * 100, 1)


def test_summarize_no_reviewer_data():
    metrics = [
        _make_metric(task_id="feat-001", status="completed"),
        _make_metric(task_id="feat-002", status="failed"),
    ]
    stats = summarize(metrics)
    assert stats["reviewer_pass_rate"] is None


def test_summarize_avg_retries():
    metrics = [
        _make_metric(task_id="feat-001", status="completed", retry_count=0),
        _make_metric(task_id="feat-002", status="completed", retry_count=2),
        _make_metric(task_id="feat-003", status="failed", retry_count=3),
    ]
    stats = summarize(metrics)
    assert stats["avg_retries"] == round((0 + 2 + 3) / 3, 2)


def test_summarize_escalated_counted():
    metrics = [
        _make_metric(task_id="feat-001", status="completed"),
        _make_metric(task_id="feat-002", status="escalated"),
    ]
    stats = summarize(metrics)
    assert stats["escalated"] == 1
    assert stats["total"] == 2
