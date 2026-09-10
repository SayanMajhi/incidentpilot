from safety.policy import policy


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