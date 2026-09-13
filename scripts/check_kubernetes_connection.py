"""Read-only connectivity check for IncidentPilot's Kubernetes mode.

Verifies, without modifying anything, that:

* the ``kubernetes`` Python package is installed,
* the active (or K8S_CONTEXT) kubeconfig context is an allow-listed local
  cluster,
* the ``incidentpilot`` namespace and the target Deployment exist, and the
  Deployment is labelled for IncidentPilot management,
* the adapter can derive metrics, version, capacity, history and logs.

Usage (from the repository root):

    python scripts/check_kubernetes_connection.py

Configuration is read from the environment / .env exactly as the backend
reads it (K8S_CONTEXT, K8S_DEPLOYMENT, ...). See docs/kubernetes.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from backend.infrastructure import InfrastructureError  # noqa: E402
from backend.infrastructure.kubernetes import KubernetesInfrastructure, KubernetesSettings  # noqa: E402


def main() -> int:
    load_dotenv()

    try:
        settings = KubernetesSettings.from_env()
        adapter = KubernetesInfrastructure(settings=settings)

        connection = adapter.check_connection()
        print(f"context      : {connection['context']}")
        print(f"namespace    : {connection['namespace']}")
        print(f"deployment   : {connection['deployment']} (managed={connection['managed']})")
        print(f"version      : {connection['version']}")
        print(f"replicas     : {connection['ready_replicas']}/{connection['replicas']} ready")

        if not connection["managed"]:
            print(
                "WARNING: the Deployment is missing the incidentpilot.io/managed=true "
                "label, so IncidentPilot will refuse to remediate it.",
                file=sys.stderr,
            )

        metrics = adapter.get_metrics()
        print(
            f"metrics      : status={metrics['status']} error_rate={metrics['error_rate']} "
            f"latency_ms={metrics['latency_ms']} ({metrics['probe_samples']} probes)"
        )
        print(f"capacity     : {adapter.get_capacity()}")
        print("history      :", [
            (record["version"], record["revision"], record["status"])
            for record in adapter.get_deployment_history()
        ])
        logs = adapter.query_logs()
        print(f"logs         : {len(logs)} entries; latest:")
        for entry in logs[-5:]:
            print(f"  [{entry['level']}] {entry['message']}")

    except InfrastructureError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("\nKubernetes connectivity OK (no resources were modified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
