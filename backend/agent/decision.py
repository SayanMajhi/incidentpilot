"""
IncidentPilot - Decision Engine
=================================

The DecisionEngine turns diagnostic *observations* (telemetry, logs,
deployment history, capacity) into a diagnosis and a single recommended next
*action*. It is purely analytical:

    - It NEVER calls anything in `backend/tools/remediation.py`.
    - It NEVER mutates simulator state.
    - It only reads the `observations` dict it is given and returns a
      structured decision describing what an operator/agent *should*
      do next. Executing that decision is the caller's job (subject to
      whatever safety policy sits between decision and execution).

The pipeline is deliberately split into three evidence-driven stages:

    1. collect_evidence()  - turn raw observations into discrete, named
                             evidence items ("logs:resource_pressure", ...).
    2. diagnose()          - rank the causal hypotheses those items support,
                             and rule out any hypothesis whose remediation was
                             already executed in this run and failed
                             verification.
    3. decide()            - propose the remediation of the strongest
                             hypothesis that is still viable, or escalate.

There is no notion of "the next step after X". What an attempt does depends
only on the evidence observed *for that attempt* plus the record of which
remediations have already been tried and verified as unsuccessful. A failed
restart does not imply scaling; it only removes restart from consideration.
If the fresh evidence then supports another cause, that cause's remediation is
proposed; if it supports nothing new, the engine escalates.

This is still a deterministic, rule-based baseline - no LLM involved.
"""

import math
from typing import Any, Dict, List, Optional, Union

from backend.shared import slo

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

# Transient-failure signals: requests timing out or being refused outright,
# with nothing more specific to explain them.
_TRANSIENT_KEYWORDS = ("timeout", "timed out", "503")

# Metrics thresholds used to decide whether error rate / latency counts as
# "elevated" evidence. These sit between the simulator's healthy baseline
# (error_rate=0.01, latency_ms=100) and its outage values
# (error_rate=0.70, latency_ms=1000), so genuine incidents clear them
# comfortably while healthy noise does not.
_ELEVATED_ERROR_RATE_THRESHOLD = slo.ELEVATED_ERROR_RATE
_ELEVATED_LATENCY_MS_THRESHOLD = slo.ELEVATED_LATENCY_MS

_HIGH_CONFIDENCE = 0.92
_MEDIUM_CONFIDENCE = 0.85
_TRANSIENT_CONFIDENCE = 0.70
_LOW_CONFIDENCE = 0.40
_UNRESOLVED_TARGET_CONFIDENCE = 0.50

# Added when a hypothesis is corroborated by more than one evidence source
# (for example logs AND capacity telemetry).
_CORROBORATION_BONUS = 0.05
_MAX_CONFIDENCE = 0.97

# Replicas added when resource pressure is evident but utilization telemetry
# is unavailable to size the step from.
_DEFAULT_SCALE_STEP = 2

DEPLOYMENT_REGRESSION = "deployment_regression"
RESOURCE_EXHAUSTION = "resource_exhaustion"
TRANSIENT_SERVICE_FAILURE = "transient_service_failure"
NO_ACTIVE_INCIDENT = "no_active_incident"
UNDETERMINED = "undetermined"

# Causal hypotheses, most specific first. Specific causal evidence (a named
# release, an exhausted pool) outranks generic symptoms (timeouts), because a
# generic symptom is also what every specific cause looks like from outside.
# The order ranks explanations of the evidence; it is not a sequence of
# actions to try.
_HYPOTHESES = (
    {
        "cause": DEPLOYMENT_REGRESSION,
        "signals": ("deployment_failure",),
        "action": "rollback_deployment",
        "confidence": _HIGH_CONFIDENCE,
    },
    {
        "cause": RESOURCE_EXHAUSTION,
        "signals": ("resource_pressure", "capacity_over_utilized"),
        "action": "scale_service",
        "confidence": _MEDIUM_CONFIDENCE,
    },
    {
        "cause": TRANSIENT_SERVICE_FAILURE,
        "signals": ("transient_failure",),
        "action": "restart_service",
        "confidence": _TRANSIENT_CONFIDENCE,
    },
)


def _log_message(entry: Union[str, Dict[str, Any]]) -> str:
    """Return the message text of a structured or plain-string log entry.

    Log entries coming from the diagnostics layer may be plain strings
    (as in hand-written test observations) or structured dicts with a
    "message" key (as returned by tools.diagnostics.query_logs()).
    """
    if isinstance(entry, dict):
        return str(entry.get("message", ""))
    return str(entry)


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


def _classify_log_line(
        message: str,
        current_version: Optional[str],
        metrics_elevated: bool,
) -> Optional[str]:
    """Attribute one log line to the most specific signal it supports.

    Each line counts toward exactly one signal. "HTTP 503 responses increased
    after deployment v42" is evidence of a deployment failure, and must not
    also be counted as independent evidence of a transient failure - the
    deployment already explains it.

    Deployment evidence requires BOTH a deployment signal (a deployment
    keyword, or the current version named explicitly) AND a failure signal
    (failure wording on the line, or elevated metrics). This deliberately
    avoids fragile heuristics like "deployment history has more than one
    entry".
    """
    text = message.lower()

    deployment_mentioned = any(keyword in text for keyword in _DEPLOYMENT_KEYWORDS)
    version_mentioned = bool(current_version) and current_version.lower() in text
    failure_signal = any(keyword in text for keyword in _ERROR_KEYWORDS) or metrics_elevated

    if (deployment_mentioned or version_mentioned) and failure_signal:
        return "deployment_failure"

    if any(keyword in text for keyword in _RESOURCE_KEYWORDS):
        return "resource_pressure"

    if any(keyword in text for keyword in _TRANSIENT_KEYWORDS):
        return "transient_failure"

    return None


def collect_evidence(observations: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn raw observations into discrete, named evidence items.

    Every item has a stable ``id`` (``"<source>:<signal>"``) so the controller
    can tell which evidence is new between attempts, the ``signal`` it
    represents, the ``source`` it came from, and a human-readable ``detail``
    quoting what was actually observed.

    Args:
        observations: A dict that may contain "metrics", "health", "logs",
            "current_version" and "capacity".

    Returns:
        list: Evidence items in a deterministic order.
    """
    metrics = observations.get("metrics") or {}
    health = observations.get("health") or {}
    capacity = observations.get("capacity") or {}
    current_version = observations.get("current_version")
    logs = observations.get("logs", []) or []

    evidence: List[Dict[str, Any]] = []

    # -- Telemetry ---------------------------------------------------------
    if health and health.get("status") not in (None, "healthy"):
        evidence.append({
            "id": "health:check_failed",
            "source": "health",
            "signal": "health_check_failed",
            "detail": f"Health check reports status '{health.get('status')}'.",
        })

    error_rate = metrics.get("error_rate")
    if isinstance(error_rate, (int, float)) and error_rate > slo.RECOVERY_MAX_ERROR_RATE:
        evidence.append({
            "id": "telemetry:error_rate_breach",
            "source": "telemetry",
            "signal": "error_rate_breach",
            "detail": (
                f"Error rate {error_rate:.1%} exceeds the "
                f"{slo.RECOVERY_MAX_ERROR_RATE:.0%} SLO."
            ),
        })

    latency_ms = metrics.get("latency_ms")
    if isinstance(latency_ms, (int, float)) and latency_ms > slo.RECOVERY_MAX_LATENCY_MS:
        evidence.append({
            "id": "telemetry:latency_breach",
            "source": "telemetry",
            "signal": "latency_breach",
            "detail": (
                f"Latency {latency_ms}ms exceeds the "
                f"{slo.RECOVERY_MAX_LATENCY_MS}ms SLO."
            ),
        })

    # -- Capacity telemetry -----------------------------------------------
    utilization = capacity.get("utilization")
    if isinstance(utilization, (int, float)) and utilization > 1.0:
        evidence.append({
            "id": "capacity:over_utilized",
            "source": "capacity",
            "signal": "capacity_over_utilized",
            "detail": (
                f"Demand is at {utilization:.0%} of provisioned capacity "
                f"across {capacity.get('replicas')} replica(s)."
            ),
            "value": utilization,
        })

    # -- Logs --------------------------------------------------------------
    metrics_elevated = _metrics_elevated(metrics)
    matched: Dict[str, List[str]] = {}
    for entry in logs:
        message = _log_message(entry)
        signal = _classify_log_line(message, current_version, metrics_elevated)
        if signal is not None:
            matched.setdefault(signal, []).append(message)

    for signal in ("deployment_failure", "resource_pressure", "transient_failure"):
        messages = matched.get(signal)
        if messages:
            evidence.append({
                "id": f"logs:{signal}",
                "source": "logs",
                "signal": signal,
                "detail": messages[0],
                "count": len(messages),
            })

    return evidence


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
    """
    if not deployment_history:
        return None

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

    return versions_oldest_first[-1]


def _normalize_history(observations: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the record of previous attempts in this run.

    The controller supplies ``attempt_history`` (one entry per attempt). A
    single legacy ``previous_attempt`` entry is accepted too.
    """
    history = observations.get("attempt_history")
    if history:
        return [entry for entry in history if isinstance(entry, dict)]

    previous_attempt = observations.get("previous_attempt")
    if isinstance(previous_attempt, dict):
        return [previous_attempt]

    return []


def _attempt_failed(entry: Dict[str, Any]) -> bool:
    """True if an attempt's remediation did not lead to verified recovery."""
    if entry.get("verification_recovered") is False:
        return True
    return entry.get("action_success") is False


def find_failed_attempt(
        action: str,
        target: Any,
        history: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Return the earlier attempt that already tried this remediation and failed.

    The same action counts as already tried when:

    * restart_service  - any earlier restart;
    * rollback_deployment - a rollback to the same version (or an unrecorded
      target);
    * scale_service    - an earlier scale to at least as many replicas, since
      scaling to fewer cannot succeed where more capacity did not.

    A remediation whose target differs meaningfully (for example scaling
    further because fresh utilization telemetry shows the first step was not
    enough) is *not* a repeat.
    """
    for entry in history:
        if entry.get("action") != action or not _attempt_failed(entry):
            continue

        previous_target = entry.get("target")

        if action == "restart_service":
            return entry

        if action == "rollback_deployment":
            if previous_target is None or previous_target == target:
                return entry

        if action == "scale_service":
            if (
                    previous_target is None
                    or target is None
                    or (isinstance(previous_target, (int, float)) and previous_target >= target)
            ):
                return entry

    return None


def _propose_remediation(
        hypothesis: Dict[str, Any],
        observations: Dict[str, Any],
        supporting: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the bounded remediation for a supported hypothesis.

    Returns a dict with "action", "target", "parameters", and - if no safe
    target can be derived from the evidence - "unavailable_reason".
    """
    action = hypothesis["action"]

    if action == "rollback_deployment":
        current_version = observations.get("current_version")
        previous_version = _find_previous_version(
            observations.get("deployment_history", []) or [],
            current_version,
        )
        proposal = {
            "action": action,
            "target": previous_version,
            "parameters": {"from_version": current_version},
        }
        if previous_version is None:
            proposal["unavailable_reason"] = (
                "Logs implicate the current deployment, but no prior "
                "stable version could be identified from deployment "
                "history, so a rollback target cannot be safely chosen."
            )
        return proposal

    if action == "scale_service":
        capacity = observations.get("capacity") or {}
        current_replicas = capacity.get("replicas") or slo.MIN_REPLICAS
        utilization = next(
            (item.get("value") for item in supporting if item["signal"] == "capacity_over_utilized"),
            None,
        )

        if utilization is not None:
            # Size the step from measured demand: enough replicas to bring
            # utilization back to at most 100%.
            desired = math.ceil(round(current_replicas * utilization, 6))
            sizing = f"sized from {utilization:.0%} utilization"
        else:
            desired = current_replicas + _DEFAULT_SCALE_STEP
            sizing = "utilization telemetry unavailable; default step"

        target = min(desired, slo.MAX_REPLICAS)
        proposal = {
            "action": action,
            "target": target,
            "parameters": {
                "current_replicas": current_replicas,
                "utilization": utilization,
                "sizing": sizing,
            },
        }
        if target <= current_replicas:
            proposal["unavailable_reason"] = (
                f"Resource pressure is evident, but the service already runs "
                f"{current_replicas} replica(s) and the safe maximum is "
                f"{slo.MAX_REPLICAS}, so no further scaling can be proposed."
            )
        return proposal

    return {"action": action, "target": None, "parameters": {}}


class DecisionEngine:
    """Analyzes diagnostic observations, diagnoses, and selects the next action.

    The DecisionEngine never executes actions itself - it only decides
    what should happen next. Executing the returned action (and any
    additional safety checks) is left to the caller / safety policy /
    remediation layer.
    """

    def diagnose(self, observations: Dict[str, Any]) -> Dict[str, Any]:
        """Rank the causal hypotheses the evidence supports.

        Args:
            observations: A dict that may contain "metrics", "health",
                "logs", "deployment_history", "current_version", "capacity",
                "evidence" (pre-collected), and "attempt_history" (or a
                legacy "previous_attempt").

        Returns:
            dict: ``probable_cause``, ``confidence`` and ``summary`` for the
            strongest viable hypothesis, plus every ``hypotheses`` entry
            (supported, ruled out, or lacking a safe remediation) and the
            ``evidence`` it was derived from.
        """
        evidence = observations.get("evidence")
        if evidence is None:
            evidence = collect_evidence(observations)

        history = _normalize_history(observations)
        signals = {item["signal"] for item in evidence}

        hypotheses: List[Dict[str, Any]] = []
        for template in _HYPOTHESES:
            supporting = [item for item in evidence if item["signal"] in template["signals"]]
            if not supporting:
                continue

            sources = {item["source"] for item in supporting}
            confidence = template["confidence"]
            if len(sources) > 1:
                confidence = min(_MAX_CONFIDENCE, confidence + _CORROBORATION_BONUS)

            proposal = _propose_remediation(template, observations, supporting)
            hypothesis = {
                "cause": template["cause"],
                "confidence": confidence,
                "evidence": [item["id"] for item in supporting],
                "remediation": {
                    "action": proposal["action"],
                    "target": proposal["target"],
                    "parameters": proposal["parameters"],
                },
                "status": "viable",
            }

            failed = find_failed_attempt(proposal["action"], proposal["target"], history)
            if "unavailable_reason" in proposal:
                hypothesis["status"] = "no_safe_remediation"
                hypothesis["status_reason"] = proposal["unavailable_reason"]
            elif failed is not None:
                hypothesis["status"] = "ruled_out"
                hypothesis["status_reason"] = (
                    f"{proposal['action']} was already executed"
                    + (f" in attempt {failed['attempt']}" if failed.get("attempt") else "")
                    + " and verification showed the service was still unhealthy."
                )

            hypotheses.append(hypothesis)

        leading = next(
            (hypothesis for hypothesis in hypotheses if hypothesis["status"] != "ruled_out"),
            None,
        )

        if leading is not None:
            details = "; ".join(
                item["detail"] for item in evidence if item["id"] in leading["evidence"]
            )
            probable_cause = leading["cause"]
            confidence = leading["confidence"]
            summary = f"Evidence indicates {probable_cause.replace('_', ' ')}: {details}"
        elif hypotheses:
            probable_cause = UNDETERMINED
            confidence = _UNRESOLVED_TARGET_CONFIDENCE
            summary = (
                "Every cause the evidence supports has already been remediated "
                "without verified recovery, and no new cause is evident."
            )
        elif signals & {"health_check_failed", "error_rate_breach", "latency_breach"}:
            probable_cause = UNDETERMINED
            confidence = _LOW_CONFIDENCE
            summary = "The service is unhealthy, but no evidence identifies a supported cause."
        else:
            probable_cause = NO_ACTIVE_INCIDENT
            confidence = _LOW_CONFIDENCE
            summary = "No incident evidence was observed."

        return {
            "probable_cause": probable_cause,
            "confidence": confidence,
            "summary": summary,
            "hypotheses": hypotheses,
            "evidence": evidence,
        }

    def decide(
            self,
            observations: Dict[str, Any],
            diagnosis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Choose the next action based on the given observations.

        Args:
            observations: See :meth:`diagnose`.
            diagnosis: A diagnosis already produced by :meth:`diagnose` for
                these observations. Computed here when omitted.

        Returns:
            dict: A structured decision with "action", "target",
            "parameters", "reason", "confidence", "diagnosis" (the probable
            cause) and "evidence" (the evidence ids that justify it).
            Possible actions are "rollback_deployment", "scale_service",
            "restart_service", and "escalate".
        """
        if diagnosis is None:
            diagnosis = self.diagnose(observations)

        hypotheses = diagnosis.get("hypotheses", [])
        evidence_by_id = {item["id"]: item for item in diagnosis.get("evidence", [])}
        ruled_out = [hypothesis for hypothesis in hypotheses if hypothesis["status"] == "ruled_out"]

        ruled_out_note = "".join(
            f" Ruled out {hypothesis['cause']}: {hypothesis['status_reason']}"
            for hypothesis in ruled_out
        )

        for hypothesis in hypotheses:
            if hypothesis["status"] == "ruled_out":
                continue

            if hypothesis["status"] == "no_safe_remediation":
                # The best explanation of the evidence has no safe fix. Do not
                # fall through to a weaker explanation just to have something
                # to do.
                return {
                    "action": "escalate",
                    "target": None,
                    "parameters": {},
                    "reason": hypothesis["status_reason"] + ruled_out_note,
                    "confidence": _UNRESOLVED_TARGET_CONFIDENCE,
                    "diagnosis": hypothesis["cause"],
                    "evidence": list(hypothesis["evidence"]),
                }

            remediation = hypothesis["remediation"]
            details = "; ".join(
                evidence_by_id[item_id]["detail"]
                for item_id in hypothesis["evidence"]
                if item_id in evidence_by_id
            )
            target_note = (
                f" -> {remediation['target']}" if remediation["target"] is not None else ""
            )
            return {
                "action": remediation["action"],
                "target": remediation["target"],
                "parameters": dict(remediation["parameters"]),
                "reason": (
                    f"Evidence indicates {hypothesis['cause'].replace('_', ' ')} "
                    f"({details}). Proposing {remediation['action']}{target_note}."
                    + ruled_out_note
                ),
                "confidence": hypothesis["confidence"],
                "diagnosis": hypothesis["cause"],
                "evidence": list(hypothesis["evidence"]),
            }

        if ruled_out:
            reason = (
                "The remediations supported by the current evidence have "
                "already been executed without verified recovery, and no new "
                "evidence justifies a different supported action."
                + ruled_out_note
            )
            confidence = _UNRESOLVED_TARGET_CONFIDENCE
        else:
            reason = "No safe remediation could be confidently determined."
            confidence = _LOW_CONFIDENCE

        return {
            "action": "escalate",
            "target": None,
            "parameters": {},
            "reason": reason,
            "confidence": confidence,
            "diagnosis": diagnosis.get("probable_cause", UNDETERMINED),
            "evidence": [item["id"] for item in diagnosis.get("evidence", [])],
        }


decision_engine = DecisionEngine()
