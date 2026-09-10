"""
IncidentPilot - Decision Engine
=================================

The DecisionEngine turns diagnostic *observations* (logs, deployment
history, current version, metrics) into a single recommended next
*action*. It is purely analytical:

    - It NEVER calls anything in `tools/remediation.py`.
    - It NEVER mutates simulator state.
    - It only reads the `observations` dict it is given and returns a
      structured decision describing what an operator/agent *should*
      do next. Executing that decision is the caller's job (subject to
      whatever safety policy sits between decision and execution).

This is still a deterministic, rule-based baseline - no LLM involved.
"""

from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Evidence keywords
# ---------------------------------------------------------------------------
# Deployment-related signals: something in the logs ties the incident to a
# deployment/release/version change.
_DEPLOYMENT_KEYWORDS = ("deployment", "deploy", "release", "rollout")

# Generic failure/error signals. On their own these say nothing about the
# *cause* of an incident - they only matter combined with a deployment
# signal (or elevated metrics) below.
_ERROR_KEYWORDS = (
    "error",
    "fail",
    "failure",
    "exception",
    "crash",
    "503",
    "500",
    "timeout",
)

# Resource-exhaustion signals.
_RESOURCE_KEYWORDS = (
    "resource",
    "memory",
    "connection pool",
    "out of memory",
    "oom",
    "cpu",
)

# Metrics thresholds used to decide whether error rate / latency counts as
# "elevated" evidence. These sit between the simulator's healthy baseline
# (error_rate=0.01, latency_ms=100) and its outage values
# (error_rate=0.70, latency_ms=1000), so genuine incidents clear them
# comfortably while healthy noise does not.
_ELEVATED_ERROR_RATE_THRESHOLD = 0.10
_ELEVATED_LATENCY_MS_THRESHOLD = 300

_HIGH_CONFIDENCE = 0.92
_MEDIUM_CONFIDENCE = 0.85
_LOW_CONFIDENCE = 0.40
_UNRESOLVED_TARGET_CONFIDENCE = 0.50


def _extract_log_text(logs: List[Union[str, Dict[str, Any]]]) -> str:
    """Flatten structured or plain-string log entries into one lowercase blob.

    Log entries coming from the diagnostics layer may be plain strings
    (as in hand-written test observations) or structured dicts with a
    "message" key (as returned by tools.diagnostics.query_logs()).
    Calling .lower() directly on a dict would raise an AttributeError,
    so every entry is normalized to its message text first.

    Args:
        logs: A list of log entries, each either a string or a dict
            with (at least) a "message" key.

    Returns:
        str: All log messages joined into a single lowercase string,
        suitable for simple substring/keyword evidence checks.
    """
    parts: List[str] = []
    for entry in logs:
        if isinstance(entry, dict):
            parts.append(str(entry.get("message", "")))
        else:
            parts.append(str(entry))
    return " ".join(parts).lower()


def _metrics_elevated(metrics: Optional[Dict[str, Any]]) -> bool:
    """Return True if the observed metrics look like an active incident.

    Args:
        metrics: A dict that may contain "error_rate" and/or
            "latency_ms", as produced by tools.diagnostics.get_metrics().

    Returns:
        bool: True if error rate or latency is elevated above the
        healthy baseline, False otherwise (including when no metrics
        were supplied).
    """
    if not metrics:
        return False

    error_rate = metrics.get("error_rate", 0) or 0
    latency_ms = metrics.get("latency_ms", 0) or 0

    return (
            error_rate > _ELEVATED_ERROR_RATE_THRESHOLD
            or latency_ms > _ELEVATED_LATENCY_MS_THRESHOLD
    )


def _has_deployment_evidence(
        log_text: str,
        current_version: Optional[str],
        metrics: Optional[Dict[str, Any]],
) -> bool:
    """Decide whether there is real evidence tying the incident to a deployment.

    Strong evidence requires BOTH:
      1. A deployment signal - either an explicit deployment/release
         keyword in the logs, or the currently deployed version being
         mentioned by name (e.g. "v42").
      2. A failure signal - explicit error/failure wording in the
         logs, OR metrics that are elevated above the healthy baseline.

    This deliberately avoids fragile heuristics like "deployment
    history has more than one entry" - the evidence has to actually be
    present in the observations, not merely inferred from history
    length.

    Args:
        log_text: Combined, lowercased log text (see _extract_log_text).
        current_version: The currently deployed version, if known.
        metrics: Optional metrics dict (error_rate/latency_ms).

    Returns:
        bool: True if there is real deployment-caused-incident evidence.
    """
    deployment_mentioned = any(keyword in log_text for keyword in _DEPLOYMENT_KEYWORDS)
    version_mentioned = bool(current_version) and current_version.lower() in log_text

    error_mentioned = any(keyword in log_text for keyword in _ERROR_KEYWORDS)
    failure_signal = error_mentioned or _metrics_elevated(metrics)

    return (deployment_mentioned or version_mentioned) and failure_signal


def _has_resource_evidence(log_text: str) -> bool:
    """Decide whether the logs point to resource exhaustion.

    Args:
        log_text: Combined, lowercased log text.

    Returns:
        bool: True if a resource-exhaustion keyword is present.
    """
    return any(keyword in log_text for keyword in _RESOURCE_KEYWORDS)


def _find_previous_version(
        deployment_history: List[Dict[str, Any]],
        current_version: Optional[str],
) -> Optional[str]:
    """Find the version deployed immediately before current_version.

    Handles the actual structure returned by
    tools.diagnostics.get_deployment_history() - a list of dicts with
    "version" and an "order" field where higher order = more recent -
    as well as simpler test-style history lists that only carry
    "version" and are already given oldest-first.

    Two cases are handled:
      1. current_version appears in the history: the entry immediately
         before it (by order) is the previous stable version.
      2. current_version is NOT in the history (e.g. it's a brand new,
         not-yet-recorded deployment - exactly how
         simulate_bad_deployment() behaves relative to
         get_deployment_history()): the most recent recorded entry is
         the last known-good version, i.e. the previous version.

    Never guesses a target when there isn't one to find - if history
    is empty, or current_version is the oldest (or only) entry, this
    returns None so the caller can escalate instead of inventing a
    rollback target.

    Args:
        deployment_history: List of deployment records.
        current_version: The currently deployed version.

    Returns:
        Optional[str]: The previous version string, or None if it
        cannot be safely determined.
    """
    if not deployment_history:
        return None

    # Sort chronologically (oldest first). Use the "order" field when every
    # record has one (the real diagnostics structure); otherwise fall back
    # to the list's given order (test-style history is already
    # oldest-to-newest).
    if all("order" in record for record in deployment_history):
        ordered = sorted(deployment_history, key=lambda record: record["order"])
    else:
        ordered = list(deployment_history)

    versions_oldest_first = [record.get("version") for record in ordered]

    if current_version in versions_oldest_first:
        index = versions_oldest_first.index(current_version)
        if index == 0:
            return None
        return versions_oldest_first[index - 1]

    # current_version isn't recorded in history at all (e.g. it's the new,
    # not-yet-committed deployment that caused the incident) - the most
    # recently recorded version is the last known-good one to roll back to.
    return versions_oldest_first[-1]


class DecisionEngine:
    """Analyzes diagnostic observations and selects the next action.

    The DecisionEngine never executes actions itself - it only decides
    what should happen next. Executing the returned action (and any
    additional safety checks) is left to the caller / safety policy /
    remediation layer.
    """

    def decide(self, observations: Dict[str, Any]) -> Dict[str, Any]:
        """Choose the next action based on the given observations.

        Args:
            observations: A dict that may contain:
                - "logs": list of log entries (str or dict with "message").
                - "deployment_history": list of deployment records.
                - "current_version": the currently deployed version string.
                - "metrics": dict with "error_rate" / "latency_ms".

        Returns:
            dict: A decision with keys "action", "target", "reason",
            and "confidence". Possible actions are
            "rollback_deployment", "scale_service", and "escalate".
        """
        logs = observations.get("logs", []) or []
        deployment_history = observations.get("deployment_history", []) or []
        current_version = observations.get("current_version")
        metrics = observations.get("metrics")

        log_text = _extract_log_text(logs)

        # 1. Bad deployment: real evidence in the logs (and/or metrics) ties
        #    the incident to the currently deployed version.
        if _has_deployment_evidence(log_text, current_version, metrics):
            previous_version = _find_previous_version(deployment_history, current_version)

            if previous_version is not None:
                return {
                    "action": "rollback_deployment",
                    "target": previous_version,
                    "reason": (
                        f"Logs show deployment-related failures on the "
                        f"current version ({current_version}); deployment "
                        f"history identifies '{previous_version}' as the "
                        "last known-good version to roll back to."
                    ),
                    "confidence": _HIGH_CONFIDENCE,
                }

            # Deployment is implicated, but there's no safe target to roll
            # back to - do not invent one. Escalate instead.
            return {
                "action": "escalate",
                "target": None,
                "reason": (
                    "Logs implicate the current deployment, but no prior "
                    "stable version could be identified from deployment "
                    "history, so a rollback target cannot be safely chosen."
                ),
                "confidence": _UNRESOLVED_TARGET_CONFIDENCE,
            }

        # 2. Resource exhaustion.
        if _has_resource_evidence(log_text):
            return {
                "action": "scale_service",
                "target": 3,
                "reason": "Logs indicate resource exhaustion.",
                "confidence": _MEDIUM_CONFIDENCE,
            }

        # 3. Nothing recognizable - don't guess, escalate to a human.
        return {
            "action": "escalate",
            "target": None,
            "reason": "No safe remediation could be confidently determined.",
            "confidence": _LOW_CONFIDENCE,
        }


decision_engine = DecisionEngine()