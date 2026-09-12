from backend.safety.policy import policy


def test_safe_restart_is_allowed():
    assert policy.allows("restart_service")


def test_safe_scale_is_allowed():
    assert policy.allows("scale_service", replicas=3)


def test_excessive_scale_is_blocked():
    assert not policy.allows("scale_service", replicas=100)


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
