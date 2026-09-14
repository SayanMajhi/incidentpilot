"""Smoke-test the optional Hugging Face/Qwen proposal provider.

This does not run the incident controller or execute infrastructure actions.
Install ``requirements-llm.txt``, set ``HF_TOKEN`` and ``HF_MODEL`` (in the
shell or an uncommitted ``.env``), then run this file from the repository root.
The normal deterministic IncidentPilot demo does not require this check.
"""

from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.config import get_settings

SYSTEM_PROMPT = (
    "You are a connectivity test. Do not provide reasoning. "
    "Your final answer must be exactly INCIDENTPILOT_QWEN_OK."
)
USER_PROMPT = "Respond with the required test string."

# Qwen3 models can spend a meaningful number of tokens on internal reasoning
# before producing a final `content` string. 16 tokens was too small and
# left `finish_reason == "length"` with `content is None`. 100 gives the
# model room to actually finish a short final answer.
MAX_TOKENS = 100
EXPECTED_REPLY = "INCIDENTPILOT_QWEN_OK"


def main() -> int:
    settings = get_settings()
    hf_token = (
        settings.hf_token.get_secret_value()
        if settings.hf_token is not None
        else None
    )
    hf_model = settings.hf_model

    if not hf_token:
        print(
            "ERROR: HF_TOKEN environment variable is not set.\n"
            "Set it in the current shell or an uncommitted .env file, then retry.",
            file=sys.stderr,
        )
        return 1

    try:
        from huggingface_hub import InferenceClient
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError:
        print(
            "ERROR: Optional Hugging Face dependencies are not installed. "
            "Run: python -m pip install -r requirements-llm.txt",
            file=sys.stderr,
        )
        return 1

    try:
        client = InferenceClient(api_key=hf_token, provider="auto")

        response = client.chat.completions.create(
            model=hf_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            max_tokens=MAX_TOKENS,
        )

        # Normal path: the model's final answer.
        message = response.choices[0].message
        reply_text = getattr(message, "content", None)

        if reply_text:
            normalized_reply = str(reply_text).strip()
            if normalized_reply == EXPECTED_REPLY:
                print(EXPECTED_REPLY)
                return 0
            print(
                "ERROR: Provider returned final content, but it did not match "
                "the required connectivity sentinel.",
                file=sys.stderr,
            )
            return 1

        # content is still None/empty. Do NOT fall back to reasoning_content
        # as the final answer — for this application, reasoning is not an
        # acceptable substitute for a structured/final response. Report a
        # clear, actionable diagnostic instead (without dumping the full
        # response object or any credentials).
        finish_reason = getattr(response.choices[0], "finish_reason", "unknown")
        has_reasoning = bool(getattr(message, "reasoning_content", None)) or bool(
            getattr(message, "reasoning", None)
        )

        print(
            "ERROR: Model did not return a final `content` response "
            f"(finish_reason={finish_reason!r}, "
            f"reasoning_present={has_reasoning}). "
            "Not using reasoning_content as a substitute answer.",
            file=sys.stderr,
        )
        return 1

    except HfHubHTTPError as e:
        # Hugging Face Hub / provider HTTP error (auth, model not found, rate
        # limit, provider unavailable, etc). Message is safe to print — the
        # SDK does not embed the token in exception text.
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        # Any other connectivity/runtime error (DNS, timeout, malformed
        # response, etc). Keep it concise; never print the token itself.
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
