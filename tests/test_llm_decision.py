"""
Tests for agent/llm_decision.py

All tests use a fake/mocked Hugging Face client. No real network calls or
Hugging Face API calls are made anywhere in this file.

Note: `decide()` funnels every failure (invalid action, bad confidence,
malformed JSON, API errors, etc.) through one `except Exception` block and
re-wraps it via `self._escalation(<failure-specific reason>)` - it does NOT
return the module-level `_SAFE_ESCALATION` constant verbatim (that constant
is currently unused by `decide()`; only its shape matters). So these tests
assert the safe-escalation *shape* - action "escalate", target None,
confidence 0.0, a non-empty reason - plus `last_status`/`last_error`, rather
than exact equality to `_SAFE_ESCALATION`.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent.llm_decision import LLMDecisionEngine


OBSERVATIONS = {
    "logs": ["deployment v42 rollout started", "500 error spike after deploy"],
    "deployment_history": [
        {"version": "v40", "order": 1},
        {"version": "v41", "order": 2},
        {"version": "v42", "order": 3},
    ],
    "current_version": "v42",
    "metrics": {"error_rate": 0.42, "latency_ms": 900},
}


def make_fake_client(content):
    """Build a fake InferenceClient whose chat.completions.create(...)
    returns an object shaped like the real Hugging Face response, with
    `.choices[0].message.content` set to `content` (a JSON string, or a
    dict that will be json-encoded for convenience)."""
    if isinstance(content, dict):
        content = json.dumps(content)

    client = MagicMock()
    fake_message = SimpleNamespace(content=content)
    fake_choice = SimpleNamespace(message=fake_message)
    fake_response = SimpleNamespace(choices=[fake_choice])
    client.chat.completions.create.return_value = fake_response
    return client


def make_engine(content, **kwargs):
    client = make_fake_client(content)
    return LLMDecisionEngine(client=client, model="test-model", api_key="fake-token", **kwargs)


def assert_safe_escalation(decision, engine, expected_last_status="failed"):
    """Shared shape-check for every failure path."""
    assert decision["action"] == "escalate"
    assert decision["target"] is None
    assert decision["confidence"] == 0.0
    assert isinstance(decision["reason"], str) and decision["reason"]
    assert engine.last_status == expected_last_status
    if expected_last_status == "failed":
        assert engine.last_error


# ---------------------------------------------------------------------------
# 1. Valid rollback decision
# ---------------------------------------------------------------------------

def test_valid_rollback_decision():
    engine = make_engine(
        {
            "action": "rollback_deployment",
            "target": "v41",
            "reason": "v42 is strongly correlated with failures.",
            "confidence": 0.94,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert decision["action"] == "rollback_deployment"
    assert decision["target"] == "v41"
    assert decision["confidence"] == pytest.approx(0.94)
    assert decision["reason"]
    assert engine.last_status == "success"
    assert engine.last_error is None


# ---------------------------------------------------------------------------
# 2. Valid scale decision
# ---------------------------------------------------------------------------

def test_valid_scale_decision():
    engine = make_engine(
        {
            "action": "scale_service",
            "target": "3",
            "reason": "Logs show resource exhaustion under load.",
            "confidence": 0.8,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert decision["action"] == "scale_service"
    assert decision["target"] == 3
    assert decision["confidence"] == pytest.approx(0.8)
    assert engine.last_status == "success"


# ---------------------------------------------------------------------------
# 3. Valid restart decision
# ---------------------------------------------------------------------------

def test_valid_restart_decision():
    engine = make_engine(
        {
            "action": "restart_service",
            "target": None,
            "reason": "Transient failure with no deployment or resource signal.",
            "confidence": 0.6,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert decision["action"] == "restart_service"
    assert decision["target"] is None
    assert engine.last_status == "success"


# ---------------------------------------------------------------------------
# 4. Valid escalation decision
# ---------------------------------------------------------------------------

def test_valid_escalation_decision():
    engine = make_engine(
        {
            "action": "escalate",
            "target": None,
            "reason": "Evidence is contradictory.",
            "confidence": 0.3,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert decision["action"] == "escalate"
    assert decision["target"] is None
    assert engine.last_status == "success"


# ---------------------------------------------------------------------------
# 5. Invalid action -> escalation
# ---------------------------------------------------------------------------

def test_invalid_action_escalates():
    engine = make_engine(
        {
            "action": "delete_database",
            "target": None,
            "reason": "not allowed",
            "confidence": 0.9,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


# ---------------------------------------------------------------------------
# 6. Confidence > 1 -> escalation
# ---------------------------------------------------------------------------

def test_confidence_above_one_escalates():
    engine = make_engine(
        {
            "action": "rollback_deployment",
            "target": "v41",
            "reason": "high confidence",
            "confidence": 1.5,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


# ---------------------------------------------------------------------------
# 7. Confidence < 0 -> escalation
# ---------------------------------------------------------------------------

def test_confidence_below_zero_escalates():
    engine = make_engine(
        {
            "action": "rollback_deployment",
            "target": "v41",
            "reason": "negative confidence",
            "confidence": -0.1,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


# ---------------------------------------------------------------------------
# 8. Missing reason -> escalation
# ---------------------------------------------------------------------------

def test_missing_reason_escalates():
    engine = make_engine(
        {
            "action": "rollback_deployment",
            "target": "v41",
            "reason": "",
            "confidence": 0.9,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


# ---------------------------------------------------------------------------
# 9. Missing rollback target -> escalation
# ---------------------------------------------------------------------------

def test_missing_rollback_target_escalates():
    engine = make_engine(
        {
            "action": "rollback_deployment",
            "target": None,
            "reason": "should have had a target",
            "confidence": 0.9,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


# ---------------------------------------------------------------------------
# 10. API exception -> escalation
# ---------------------------------------------------------------------------

def test_api_exception_escalates():
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("network down")
    engine = LLMDecisionEngine(client=client, model="test-model", api_key="fake-token")

    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)
    assert "network down" in engine.last_error


# ---------------------------------------------------------------------------
# 11. Missing HF_TOKEN -> escalation
# ---------------------------------------------------------------------------

def test_missing_token_escalates(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    client = make_fake_client(
        {
            "action": "rollback_deployment",
            "target": "v41",
            "reason": "should never be reached",
            "confidence": 0.9,
        }
    )
    engine = LLMDecisionEngine(client=client, model="test-model", api_key=None)

    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine, expected_last_status="missing_token")
    # The client must never be called when there is no token.
    client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# 12. Malformed structured response -> escalation
# ---------------------------------------------------------------------------

def test_malformed_json_response_escalates():
    engine = make_engine("not valid json {{{")
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


# ---------------------------------------------------------------------------
# Extra edge cases
# ---------------------------------------------------------------------------

def test_empty_content_escalates():
    engine = make_engine("")
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


def test_scale_without_valid_numeric_target_escalates():
    engine = make_engine(
        {
            "action": "scale_service",
            "target": "not-a-number",
            "reason": "resource exhaustion",
            "confidence": 0.8,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


def test_escalate_with_nonnull_target_escalates():
    engine = make_engine(
        {
            "action": "escalate",
            "target": "v41",
            "reason": "should not have a target",
            "confidence": 0.5,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


def test_restart_with_target_escalates():
    engine = make_engine(
        {
            "action": "restart_service",
            "target": "instance-1",
            "reason": "should not target a specific instance",
            "confidence": 0.5,
        }
    )
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)


def test_response_format_type_error_falls_back_and_still_succeeds():
    """If the installed client/provider doesn't accept response_format,
    the engine retries once without it instead of failing outright."""
    call_count = {"n": 0}

    def create(**kwargs):
        call_count["n"] += 1
        if "response_format" in kwargs:
            raise TypeError("unexpected keyword argument 'response_format'")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "action": "escalate",
                                "target": None,
                                "reason": "insufficient evidence",
                                "confidence": 0.2,
                            }
                        )
                    )
                )
            ]
        )

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    engine = LLMDecisionEngine(client=client, model="test-model", api_key="fake-token")

    decision = engine.decide(OBSERVATIONS)
    assert decision["action"] == "escalate"
    assert engine.last_status == "success"
    assert call_count["n"] == 2


def test_missing_model_escalates():
    """No injected client and no HF_MODEL configured should fail safely
    when a real client is built, rather than raising out of decide()."""
    engine = LLMDecisionEngine(client=None, model=None, api_key="fake-token")
    decision = engine.decide(OBSERVATIONS)
    assert_safe_escalation(decision, engine)