"""Run the normal IncidentPilot loop and persist a compact scenario audit."""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Running a file under scripts/ puts that directory first on sys.path. Add the
# repository root so the normal backend package is importable without install.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.agent.controller import IncidentController


def compact_attempt(attempt: dict) -> dict:
    """Keep the action, policy verdict, wait result, and verification."""
    return {
        "attempt": attempt.get("attempt"),
        "diagnosis": attempt.get("diagnosis", {}).get("probable_cause"),
        "action": attempt.get("decision", {}).get("action"),
        "target": attempt.get("decision", {}).get("target"),
        "safety_allowed": attempt.get("safety_result", {}).get("allowed"),
        "action_success": attempt.get("action_result", {}).get("success"),
        "reconciliation": attempt.get("action_result", {}).get("reconciliation"),
        "recovered": getattr(attempt.get("verification"), "recovered", None),
    }


if __name__ == "__main__":
    result = IncidentController(use_llm=False).run_incident()
    summary = {
        "status": result["status"],
        "attempts": [compact_attempt(attempt) for attempt in result["attempts"]],
    }
    output = Path(".incidentpilot-kubernetes-run.json")
    output.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
