"""Concurrency and live-state guarantees for the asynchronous runtime."""

from __future__ import annotations

import time
from threading import Event

import pytest

from backend.api.runtime import IncidentRuntime, RuntimeBusyError


def _wait_until_complete(runtime: IncidentRuntime, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = runtime.snapshot()
        if not snapshot["agent"]["running"]:
            return snapshot
        time.sleep(0.005)
    raise AssertionError("background incident did not complete")


def test_runtime_exposes_live_events_and_final_result():
    runtime = IncidentRuntime()

    class Controller:
        def run_incident(self, on_event, run_id, goal, started_at):
            event = {
                "event_id": "evt-live",
                "timestamp": started_at,
                "incident_id": run_id,
                "attempt": 1,
                "phase": "observing",
                "event_type": "observation_started",
                "message": "Reading telemetry.",
                "data": {},
            }
            on_event("observing", {"attempt": 1, "status": "running", "event": event})
            return {
                "run_id": run_id,
                "incident_id": run_id,
                "goal": goal,
                "started_at": started_at,
                "completed_at": started_at,
                "status": "no_incident",
                "phase": "complete",
                "attempt": 0,
                "attempts": [],
                "timeline": [event],
                "reason": "healthy",
            }

    started = runtime.start(controller=Controller(), goal="test", max_attempts=3)
    assert started["status"] == "running"
    final = _wait_until_complete(runtime)
    timeline = runtime.timeline()

    assert final["agent"]["status"] == "no_incident"
    assert final["latest_incident"]["run_id"] == started["run_id"]
    assert timeline["events"][0]["event_type"] == "observation_started"
    assert timeline["revision"] == final["revision"]


def test_runtime_rejects_reset_and_scenario_changes_while_running():
    runtime = IncidentRuntime()
    entered = Event()
    release = Event()

    class SlowController:
        def run_incident(self, on_event, run_id, goal, started_at):
            entered.set()
            assert release.wait(timeout=2)
            return {
                "run_id": run_id,
                "status": "no_incident",
                "phase": "complete",
                "attempts": [],
                "timeline": [],
                "reason": "healthy",
            }

    runtime.start(controller=SlowController(), goal="test", max_attempts=3)
    assert entered.wait(timeout=1)

    with pytest.raises(RuntimeBusyError):
        runtime.reset()
    with pytest.raises(RuntimeBusyError):
        runtime.mutate_scenario("outage", lambda: None)
    with pytest.raises(RuntimeBusyError):
        runtime.start(controller=SlowController(), goal="test", max_attempts=3)

    release.set()
    assert _wait_until_complete(runtime)["agent"]["running"] is False


def test_unexpected_controller_defect_becomes_failed_runtime_state():
    runtime = IncidentRuntime()

    class BrokenController:
        def run_incident(self, **_kwargs):
            raise RuntimeError("private detail")

    runtime.start(controller=BrokenController(), goal="test", max_attempts=3)
    final = _wait_until_complete(runtime)

    assert final["agent"]["status"] == "failed"
    assert final["latest_incident"]["status"] == "failed"
    assert runtime.timeline()["events"][-1]["event_type"] == "internal_error"

