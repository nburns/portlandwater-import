"""Tests for status.py — pure logic, no HA connections needed."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from portlandwater_import.status import (
    GRACE_DAYS,
    LastRun,
    compute,
    load_last_run,
    save_last_run,
)

_NOW = datetime(2026, 1, 18, 12, 0, 0, tzinfo=timezone.utc)


def _state(latest_interval_start=None):
    return SimpleNamespace(latest_interval_start=latest_interval_start)


def test_compute_up_to_date():
    state = _state(latest_interval_start=_NOW)
    snap = compute(state, LastRun(ok=True), None, _NOW)
    assert snap.state == "up-to-date"
    assert snap.newest_data_date == _NOW.date().isoformat()


def test_compute_backfilling_when_stale():
    stale = _NOW - timedelta(days=150)
    state = _state(latest_interval_start=stale)
    snap = compute(state, LastRun(ok=True), None, _NOW)
    assert snap.state == "backfilling"


def test_compute_backfilling_when_missing():
    state = _state(latest_interval_start=None)
    snap = compute(state, LastRun(), None, _NOW)
    assert snap.state == "backfilling"
    assert snap.newest_data_date is None


def test_compute_error_from_last_run():
    state = _state(latest_interval_start=_NOW)
    snap = compute(state, LastRun(ok=False, error="boom"), None, _NOW)
    assert snap.state == "error"
    assert snap.last_error == "boom"
    assert snap.last_error_at == snap.last_run_finished_at


def test_last_run_roundtrip(tmp_path):
    path = tmp_path / "last_run.json"
    lr = LastRun(
        started_at="2026-01-18T12:00:00+00:00",
        finished_at="2026-01-18T12:05:00+00:00",
        mode="incremental",
        ok=True,
        error=None,
    )
    save_last_run(lr, path)
    loaded = load_last_run(path)
    assert loaded.started_at == lr.started_at
    assert loaded.finished_at == lr.finished_at
    assert loaded.mode == lr.mode
    assert loaded.ok is True
    assert loaded.error is None


def test_last_run_missing_returns_default(tmp_path):
    path = tmp_path / "nonexistent.json"
    lr = load_last_run(path)
    assert lr.ok is None
    assert lr.started_at is None
    assert lr.error is None


def test_last_run_corrupt_returns_default(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not valid json{{{{")
    lr = load_last_run(path)
    assert lr.ok is None
    assert lr.started_at is None


def test_next_run_from_cron():
    # "0 6 * * 0" = every Sunday at 06:00.
    # _NOW is 2026-01-18 (Sunday) 12:00 UTC — already past 06:00 that day.
    # Next occurrence is 2026-01-25 (next Sunday) at 06:00.
    snap = compute(_state(latest_interval_start=_NOW), LastRun(ok=True), "0 6 * * 0", _NOW)
    assert snap.next_run_at is not None
    next_dt = datetime.fromisoformat(snap.next_run_at)
    assert next_dt.weekday() == 6  # Sunday
    assert next_dt.hour == 6
    assert next_dt.minute == 0
    assert next_dt.year == 2026
    assert next_dt.month == 1
    assert next_dt.day == 25
