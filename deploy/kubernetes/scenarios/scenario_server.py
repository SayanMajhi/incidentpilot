"""Small deterministic HTTP workload used by local Kubernetes scenarios.

The app deliberately models only three SRE failure modes.  Its readiness
endpoint always succeeds so a Service can route to the pod while the workload
endpoint reports the incident condition.  That lets IncidentPilot observe a
real HTTP failure, inspect the pod logs, and exercise a real Deployment
restart, rollback, or scale operation.
"""

from __future__ import annotations

import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MODE = os.getenv("MODE", "healthy")
RESTARTED_AT = os.getenv("RESTARTED_AT", "").strip()
PEER_SERVICE = os.getenv("PEER_SERVICE", "incidentpilot-demo-peers")
PEER_THRESHOLD = int(os.getenv("PEER_THRESHOLD", "3"))


def peer_count() -> int:
    """Return the number of pod IPs published by the headless peer Service."""
    try:
        addresses = socket.getaddrinfo(
            PEER_SERVICE,
            80,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return 0
    return len({entry[4][0] for entry in addresses})


def workload_state() -> tuple[int, str]:
    """Return the root-endpoint status and evidence line for the active mode."""
    if MODE == "restart":
        if not RESTARTED_AT:
            return 503, "HTTP 503 timeout: transient worker failure; restart required."
        return 200, "Restarted worker is healthy."

    if MODE == "bad-deployment":
        return 503, "Deployment v42 introduced application failures: HTTP 503."

    if MODE == "adaptive-resource-pressure":
        if not RESTARTED_AT:
            return 503, "HTTP 503 timeout: transient worker failure; restart required."
        peers = peer_count()
        if peers < PEER_THRESHOLD:
            return (
                503,
                "Resource pressure: connection pool exhausted across "
                f"{peers}/{PEER_THRESHOLD} replica(s).",
            )
        return 200, f"Capacity healthy across {peers} replica(s)."

    return 200, "Healthy scenario workload."


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required stdlib handler name
        if self.path == "/ready":
            status, message = 200, "Readiness endpoint is healthy."
        else:
            status, message = workload_state()

        print(message, flush=True)
        body = (message + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep pod logs focused on evidence rather than access-log noise."""


if __name__ == "__main__":
    print(
        f"Scenario workload started: mode={MODE}, restarted={bool(RESTARTED_AT)}.",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
