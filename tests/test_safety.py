from backend.safety.policy import policy


def test_safe_restart_is_allowed():
    assert policy.allows("restart_service")


def test_safe_scale_is_allowed():
    assert policy.allows("scale_service", replicas=3)


def test_excessive_scale_is_blocked():
    assert not policy.allows("scale_service", replicas=100)
    assert not policy.allows("scale_service", replicas=4)


def test_wrong_namespace_is_blocked():
    assert not policy.allows("restart_service", namespace="default")
    assert policy.allows("restart_service", namespace="incidentpilot")


def test_database_delete_is_blocked():
    assert not policy.allows("delete_database")


def test_scale_without_replicas_is_blocked():
    assert not policy.allows("scale_service")


def test_unknown_action_is_blocked():
    assert not policy.allows("format_database")

def test_policy_and_executor_agree_on_replica_bounds():
    """The gate must never approve a replica count the executor rejects:
    that combination previously surfaced in the dashboard as an allowed
    action that had silently failed."""
    from backend.tools import remediation

    assert policy.MAX_REPLICAS == remediation.MAX_REPLICAS
    assert policy.MIN_REPLICAS == remediation.MIN_REPLICAS

    for replicas in range(0, remediation.MAX_REPLICAS + 4):
        if policy.allows("scale_service", replicas=replicas):
            assert remediation.scale_service(replicas)["success"] is True

    remediation.reset_replicas()


def test_non_integer_replica_targets_are_blocked():
    assert not policy.allows("scale_service", replicas="3")
    assert not policy.allows("scale_service", replicas=3.5)
    assert not policy.allows("scale_service", replicas=True)
    assert not policy.allows("scale_service", replicas=None)


def test_blank_rollback_version_is_blocked():
    assert not policy.allows("rollback_deployment", version="")
    assert not policy.allows("rollback_deployment", version="   ")
    assert policy.allows("rollback_deployment", version="v41")


def test_unknown_actions_are_denied_by_default():
    assert not policy.allows("drop_table")
    assert not policy.allows("")


def test_safety_decision_explains_upper_bound_and_attempt_budget():
    decision = policy.evaluate(
        action="scale_service",
        replicas=20,
        namespace="incidentpilot",
        attempt=1,
        max_attempts=3,
    )

    assert decision.allowed is False
    assert decision.rule_id == "replica_upper_bound"
    assert decision.bounds == {"min_replicas": 1, "max_replicas": 3}
    assert decision.budget.to_dict() == {
        "attempt": 1,
        "maximum": 3,
        "remaining_after_this_attempt": 2,
    }
    assert "1-3" in decision.reason


def test_attempt_budget_is_enforced_before_action_approval():
    decision = policy.evaluate(
        action="restart_service",
        attempt=4,
        max_attempts=3,
    )

    assert decision.allowed is False
    assert decision.rule_id == "attempt_budget"


def test_rollback_target_must_come_from_history_when_history_is_available():
    history = [{"version": "v40"}, {"version": "v41"}]

    allowed = policy.evaluate(
        action="rollback_deployment",
        version="v41",
        current_version="v42",
        deployment_history=history,
    )
    unknown = policy.evaluate(
        action="rollback_deployment",
        version="v39",
        current_version="v42",
        deployment_history=history,
    )
    same = policy.evaluate(
        action="rollback_deployment",
        version="v42",
        current_version="v42",
        deployment_history=history,
    )

    assert allowed.allowed is True
    assert allowed.rule_id == "rollback_history"
    assert unknown.allowed is False
    assert unknown.rule_id == "rollback_history"
    assert same.allowed is False
    assert same.rule_id == "rollback_changes_version"


def test_namespace_rejection_carries_policy_evidence():
    decision = policy.evaluate(
        action="restart_service",
        namespace="default",
    )

    assert decision.allowed is False
    assert decision.rule_id == "namespace_allowlist"
    assert decision.namespace == "default"


def test_unreadable_history_is_not_reported_as_an_unknown_version():
    """An unreachable environment must not be denied with a rollback-history
    reason, which would blame the version for an infrastructure outage."""
    decision = policy.evaluate(
        "rollback_deployment",
        version="v41",
        namespace="incidentpilot",
        deployment_history=None,
        current_version="v42",
    )

    assert decision.allowed is True
    assert decision.rule_id == "rollback_history"


def test_empty_history_still_denies_an_unknown_rollback_target():
    decision = policy.evaluate(
        "rollback_deployment",
        version="v41",
        namespace="incidentpilot",
        deployment_history=[],
        current_version="v42",
    )

    assert decision.allowed is False
    assert decision.rule_id == "rollback_history"
