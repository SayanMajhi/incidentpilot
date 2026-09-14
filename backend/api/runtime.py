"""Synchronized, single-process runtime for incident execution.

One lock owns scenario changes, reset, run lifecycle, current result, timeline,
and revision. The controller executes on a single background worker so API
requests return immediately and clients can observe real progress.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable
from uuid import uuid4


logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class RuntimeBusyError(RuntimeError):
    """A mutating request conflicts with the active incident run."""


class IncidentRuntime:
    """Own the latest run and serialize all externally requested mutations."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="incidentpilot")
        self._revision = 0
        self._scenario = "healthy"
        self._run: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []
        self._attempts: list[dict[str, Any]] = []
        self._agent = self._idle_agent()

    @staticmethod
    def _idle_agent() -> dict[str, Any]:
        return {
            "run_id": None,
            "goal": None,
            "started_at": None,
            "updated_at": _now(),
            "running": False,
            "status": "idle",
            "phase": "idle",
            "attempt": 0,
            "max_attempts": 3,
            "reason": None,
        }

    def _bump(self) -> None:
        self._revision += 1
        self._agent["updated_at"] = _now()

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._agent["running"])

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def reset(self, *, scenario: str = "healthy") -> None:
        with self._lock:
            if self._agent["running"]:
                raise RuntimeBusyError("Cannot reset while an incident run is active.")
            self._scenario = scenario
            self._run = None
            self._events = []
            self._attempts = []
            self._agent = self._idle_agent()
            self._bump()

    def mutate_scenario(self, scenario: str, mutation: Callable[[], Any]) -> Any:
        with self._lock:
            if self._agent["running"]:
                raise RuntimeBusyError(
                    "Cannot change the simulator while an incident run is active."
                )
            result = mutation()
            self._scenario = scenario
            self._run = None
            self._events = []
            self._attempts = []
            self._agent = self._idle_agent()
            self._bump()
            return result

    def start(self, *, controller: Any, goal: str, max_attempts: int) -> dict[str, Any]:
        with self._lock:
            if self._agent["running"]:
                raise RuntimeBusyError("An incident run is already in progress.")

            run_id = f"inc-{uuid4().hex}"
            started_at = _now()
            self._events = []
            self._attempts = []
            self._run = {
                "run_id": run_id,
                "incident_id": run_id,
                "goal": goal,
                "started_at": started_at,
                "completed_at": None,
                "phase": "observing",
                "status": "running",
                "attempt": 0,
                "attempts": [],
                "timeline": [],
                "trace_events": [],
                "reason": None,
            }
            self._agent = {
                "run_id": run_id,
                "goal": goal,
                "started_at": started_at,
                "updated_at": started_at,
                "running": True,
                "status": "running",
                "phase": "observing",
                "attempt": 0,
                "max_attempts": max_attempts,
                "reason": None,
            }
            self._bump()
            self._executor.submit(
                self._execute,
                controller,
                run_id,
                goal,
                started_at,
            )
            return {
                "run_id": run_id,
                "status": "running",
                "status_url": "/status",
                "timeline_url": "/timeline",
            }

    def _on_event(self, phase: str, details: dict[str, Any] | None = None) -> None:
        details = _plain(details or {})
        with self._lock:
            self._agent["phase"] = phase
            for key in ("run_id", "goal", "started_at", "status", "attempt", "reason"):
                if key in details:
                    self._agent[key] = details[key]

            event = details.get("event")
            if event:
                event_id = event.get("event_id")
                if not event_id or all(item.get("event_id") != event_id for item in self._events):
                    self._events.append(event)

            history = details.get("history") or details.get("attempts")
            if isinstance(history, list):
                self._attempts = history

            if self._run is not None:
                self._run.update({
                    "phase": phase,
                    "status": self._agent.get("status", "running"),
                    "attempt": self._agent.get("attempt", 0),
                    "reason": self._agent.get("reason"),
                    "attempts": deepcopy(self._attempts),
                    "history": deepcopy(self._attempts),
                    "timeline": deepcopy(self._events),
                    "trace_events": deepcopy(self._events),
                })
            self._bump()

    def _execute(self, controller: Any, run_id: str, goal: str, started_at: str) -> None:
        try:
            result = controller.run_incident(
                on_event=self._on_event,
                run_id=run_id,
                goal=goal,
                started_at=started_at,
            )
            result = _plain(result)
            if not isinstance(result, dict):
                raise TypeError("Incident controller returned an invalid result.")
            with self._lock:
                self._run = result
                self._events = list(
                    result.get("timeline") or result.get("trace_events") or self._events
                )
                self._attempts = list(result.get("attempts") or result.get("history") or [])
                self._agent.update({
                    "running": False,
                    "status": result.get("status", "failed"),
                    "phase": result.get("phase", "complete"),
                    "attempt": result.get("attempt", len(self._attempts)),
                    "reason": result.get("reason"),
                })
                self._bump()
        except Exception as error:  # unexpected defects become visible state
            logger.exception("Incident controller execution failed")
            failed_at = _now()
            event = {
                "event_id": f"evt-{uuid4().hex}",
                "timestamp": failed_at,
                "incident_id": run_id,
                "attempt": self._agent.get("attempt", 0),
                "phase": "failed",
                "event_type": "internal_error",
                "message": "Incident execution stopped because of an internal error.",
                "data": {"error_type": type(error).__name__},
            }
            with self._lock:
                self._events.append(event)
                self._run = {
                    "run_id": run_id,
                    "incident_id": run_id,
                    "goal": goal,
                    "started_at": started_at,
                    "completed_at": failed_at,
                    "phase": "complete",
                    "status": "failed",
                    "attempt": self._agent.get("attempt", 0),
                    "attempts": deepcopy(self._attempts),
                    "history": deepcopy(self._attempts),
                    "timeline": deepcopy(self._events),
                    "trace_events": deepcopy(self._events),
                    "reason": "Unexpected internal error; inspect backend logs.",
                }
                self._agent.update({
                    "running": False,
                    "status": "failed",
                    "phase": "complete",
                    "reason": self._run["reason"],
                })
                self._bump()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._revision,
                "scenario": self._scenario,
                "agent": deepcopy(self._agent),
                "latest_incident": deepcopy(self._run),
            }

    def timeline(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._revision,
                "run_id": self._agent.get("run_id"),
                "status": self._agent.get("status", "idle"),
                "goal": self._agent.get("goal"),
                "started_at": self._agent.get("started_at"),
                "reason": self._agent.get("reason"),
                "events": deepcopy(self._events),
                "attempts": deepcopy(self._attempts),
            }

    def record_events(self, events: list[dict[str, Any]]) -> None:
        """Persist non-executing audit events such as a policy challenge."""
        with self._lock:
            for event in events:
                value = _plain(event)
                event_id = value.get("event_id")
                if not event_id or all(item.get("event_id") != event_id for item in self._events):
                    self._events.append(value)
            self._bump()


runtime = IncidentRuntime()
