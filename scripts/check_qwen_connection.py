"""
Temporary, isolated connectivity check for Hugging Face Inference Providers + Qwen.

This script is NOT part of the IncidentPilot agent architecture. It does not
import or touch DecisionEngine, IncidentController, SafetyPolicy, or any other
agent module. Its only purpose is to confirm, from the command line, that:

    HF_TOKEN and HF_MODEL are set correctly, and
    InferenceClient(...).chat.completions.create(...) can reach the model
    and return a usable final answer (not just reasoning).

Delete or move this script once the real LLMDecisionEngine integration lands.

Usage (via a local .env file, loaded automatically):
    # .env (not committed)
    HF_TOKEN=hf_xxx
    HF_MODEL=Qwen/Qwen3-32B

    python scripts/test_qwen_connection.py

Usage (via shell environment variables, still works):
    export HF_TOKEN=hf_xxx
    export HF_MODEL=Qwen/Qwen3-32B   # optional, defaults to this value
    python scripts/test_qwen_connection.py
"""

import os
import sys

from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError

load_dotenv()

DEFAULT_MODEL = "Qwen/Qwen3-32B"

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


def main() -> int:
    hf_token = os.getenv("HF_TOKEN")
    hf_model = os.getenv("HF_MODEL") or DEFAULT_MODEL

    if not hf_token:
        print(
            "ERROR: HF_TOKEN environment variable is not set.\n"
            "Set it before running this script, e.g.:\n"
            "  export HF_TOKEN=hf_your_token_here",
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
            print(reply_text)
            return 0

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