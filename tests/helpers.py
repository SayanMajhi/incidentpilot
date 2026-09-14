"""Shared helpers for the API-level tests."""

from __future__ import annotations

import time
from typing import Any

from backend.api.runtime import runtime
from backend.simulator.environment import simulator


def reset_simulator() -> None:
    """Return the simulator and the runtime to their idle baseline."""
    runtime.reset()
    simulator.reset()


def wait_for_idle(timeout: float = 10.0) -> None:
    """Block until the background worker has finished the current run."""
    deadline = time.monotonic() + timeout
    while runtime.running:
        if time.monotonic() > deadline:
            raise AssertionError("Incident run did not finish within the timeout.")
        time.sleep(0.01)


def run_incident(client: Any, timeout: float = 10.0) -> dict[str, Any]:
    """Start a run through the API and return the completed run record.

    ``POST /run-incident`` is asynchronous and answers 202 with a run ID, so
    every assertion about a finished run has to wait for the worker first.
    """
    response = client.post("/run-incident")
    assert response.status_code == 202, response.text
    accepted = response.json()
    wait_for_idle(timeout)
    latest = client.get("/status").json()["latest_incident"]
    assert latest is not None, "The run finished without recording a result."
    assert latest["run_id"] == accepted["run_id"]
    return latest
