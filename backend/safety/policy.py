"""Deterministic, explainable safety gate for every remediation proposal."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from backend.config import IncidentPilotSettings, get_settings
from backend.models import ActionProposal, ActionType, SafetyDecision


_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_MUTATING_ACTIONS = {
    ActionType.RESTART_SERVICE.value,
    ActionType.ROLLBACK_DEPLOYMENT.value,
    ActionType.SCALE_SERVICE.value,
}


class SafetyPolicy:
    """Allow only bounded mutations in IncidentPilot's owned namespace."""

    def __init__(self, settings: IncidentPilotSettings | None = None) -> None:
        self.settings = settings or get_settings()
        # Compatibility attributes used by the executor and existing tests.
        self.ALLOWED_NAMESPACE = self.settings.allowed_namespace
        self.MIN_REPLICAS = self.settings.min_replicas
        self.MAX_REPLICAS = self.settings.max_replicas

    def evaluate(
        self,
        proposal: ActionProposal | Mapping[str, Any] | str | None = None,
        context: Mapping[str, Any] | None = None,
        *,
        action: str | ActionType | None = None,
        target: Any = None,
        replicas: Any = None,
        version: Any = None,
        namespace: str | None = None,
        attempt: int | None = None,
        max_attempts: int | None = None,
        maximum_attempts: int | None = None,
        deployment_history: list[Mapping[str, Any]] | None = None,
        current_version: str | None = None,
    ) -> SafetyDecision:
        """Evaluate a proposal and return the exact deterministic rule result.

        The broad input form keeps policy use convenient at HTTP, controller,
        and compatibility boundaries; every branch returns the same typed
        evidence.  Supplying deployment history makes rollback validation
        strict: the requested target must be a known version.
        """
        proposal_data: dict[str, Any] = {}
        if isinstance(proposal, ActionProposal):
            proposal_data = proposal.model_dump(mode="python")
        elif isinstance(proposal, Mapping):
            proposal_data = dict(proposal)
        elif isinstance(proposal, str):
            proposal_data = {"action": proposal}

        context_data = dict(context or {})
        raw_action = action if action is not None else proposal_data.get("action", "")
        if isinstance(raw_action, ActionType):
            action_name = raw_action.value
        else:
            action_name = str(raw_action or "")

        resolved_namespace = str(
            namespace
            if namespace is not None
            else context_data.get("namespace", self.ALLOWED_NAMESPACE)
        )
        resolved_attempt = self._integer_or_default(
            attempt if attempt is not None else context_data.get("attempt"),
            1,
        )
        resolved_max_attempts = self._integer_or_default(
            max_attempts
            if max_attempts is not None
            else maximum_attempts
            if maximum_attempts is not None
            else context_data.get("max_attempts"),
            self.settings.max_attempts,
        )
        # Never let a caller widen the configured automatic-remediation budget.
        resolved_max_attempts = min(resolved_max_attempts, self.settings.max_attempts)
        resolved_max_attempts = max(1, resolved_max_attempts)

        resolved_target = target if target is not None else proposal_data.get("target")
        parameters = proposal_data.get("parameters") or {}
        if action_name == ActionType.SCALE_SERVICE.value:
            resolved_target = (
                replicas
                if replicas is not None
                else resolved_target
                if resolved_target is not None
                else parameters.get("replicas")
            )
        elif action_name == ActionType.ROLLBACK_DEPLOYMENT.value:
            resolved_target = (
                version
                if version is not None
                else resolved_target
                if resolved_target is not None
                else parameters.get("version")
            )

        resolved_history = deployment_history
        if resolved_history is None:
            resolved_history = context_data.get("deployment_history")
        resolved_current_version = current_version
        if resolved_current_version is None:
            resolved_current_version = context_data.get("current_version")

        base = {
            "action": action_name,
            "target": resolved_target,
            "namespace": resolved_namespace,
            "checked": True,
            "bounds": {
                "min_replicas": self.MIN_REPLICAS,
                "max_replicas": self.MAX_REPLICAS,
            },
            "budget": {
                "attempt": max(0, resolved_attempt),
                "maximum": resolved_max_attempts,
                "remaining_after_this_attempt": max(
                    0, resolved_max_attempts - max(0, resolved_attempt)
                ),
            },
            "context": {
                "current_version": resolved_current_version,
                "known_versions": self._known_versions(resolved_history),
            },
        }

        if resolved_attempt < 1 or resolved_attempt > resolved_max_attempts:
            return SafetyDecision(
                **base,
                allowed=False,
                rule_id="attempt_budget",
                reason=(
                    f"Attempt {resolved_attempt} is outside the configured automatic "
                    f"remediation budget of 1-{resolved_max_attempts}."
                ),
            )

        if resolved_namespace != self.ALLOWED_NAMESPACE:
            return SafetyDecision(
                **base,
                allowed=False,
                rule_id="namespace_allowlist",
                reason=(
                    f"Namespace {resolved_namespace!r} is not allowed; IncidentPilot "
                    f"may only mutate {self.ALLOWED_NAMESPACE!r}."
                ),
            )

        if action_name not in _MUTATING_ACTIONS:
            return SafetyDecision(
                **base,
                allowed=False,
                rule_id="action_allowlist",
                reason=f"Action {action_name!r} is not in the remediation allow-list.",
            )

        if action_name == ActionType.RESTART_SERVICE.value:
            return SafetyDecision(
                **base,
                allowed=True,
                rule_id="restart_service_allowed",
                reason=(
                    "A bounded service restart is allowed in the owned namespace "
                    f"during attempt {resolved_attempt} of {resolved_max_attempts}."
                ),
            )

        if action_name == ActionType.SCALE_SERVICE.value:
            if not isinstance(resolved_target, int) or isinstance(resolved_target, bool):
                return SafetyDecision(
                    **base,
                    allowed=False,
                    rule_id="replica_target_type",
                    reason="Scale target must be an integer replica count.",
                )
            if resolved_target < self.MIN_REPLICAS:
                return SafetyDecision(
                    **base,
                    allowed=False,
                    rule_id="replica_lower_bound",
                    reason=(
                        f"Scale target {resolved_target} is outside the allowed range "
                        f"{self.MIN_REPLICAS}-{self.MAX_REPLICAS}."
                    ),
                )
            if resolved_target > self.MAX_REPLICAS:
                return SafetyDecision(
                    **base,
                    allowed=False,
                    rule_id="replica_upper_bound",
                    reason=(
                        f"Scale target {resolved_target} is outside the allowed range "
                        f"{self.MIN_REPLICAS}-{self.MAX_REPLICAS}."
                    ),
                )
            return SafetyDecision(
                **base,
                allowed=True,
                rule_id="replica_bounds",
                reason=(
                    f"Scale target {resolved_target} is within the allowed range "
                    f"{self.MIN_REPLICAS}-{self.MAX_REPLICAS}."
                ),
            )

        if not isinstance(resolved_target, str) or not _VERSION.fullmatch(resolved_target):
            return SafetyDecision(
                **base,
                allowed=False,
                rule_id="rollback_target_format",
                reason="Rollback target must be a non-empty, valid version identifier.",
            )
        if resolved_current_version and resolved_target == resolved_current_version:
            return SafetyDecision(
                **base,
                allowed=False,
                rule_id="rollback_changes_version",
                reason="Rollback target must differ from the currently running version.",
            )
        known_versions = self._known_versions(resolved_history)
        if resolved_history is not None and resolved_target not in known_versions:
            return SafetyDecision(
                **base,
                allowed=False,
                rule_id="rollback_history",
                reason=(
                    f"Rollback target {resolved_target!r} is not present in deployment history."
                ),
            )
        return SafetyDecision(
            **base,
            allowed=True,
            rule_id="rollback_history",
            reason=(
                f"Rollback target {resolved_target!r} has a valid version identifier"
                + (" and appears in deployment history." if resolved_history is not None else ".")
            ),
        )

    def allows(self, action: str, **kwargs: Any) -> bool:
        """Return only the verdict. Use ``evaluate`` when the reason matters."""
        return self.evaluate(action=action, **kwargs).allowed is True

    @staticmethod
    def _integer_or_default(value: Any, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _known_versions(
        deployment_history: list[Mapping[str, Any]] | None,
    ) -> list[str]:
        if deployment_history is None:
            return []
        return [
            str(record["version"])
            for record in deployment_history
            if record.get("version") is not None
        ]


policy = SafetyPolicy()
