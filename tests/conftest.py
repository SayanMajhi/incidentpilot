"""Shared pytest configuration.

The normal suite always runs against the in-memory simulator, even if a
developer's shell or .env selects Kubernetes. Environment variables set here
take precedence over .env, because python-dotenv never overrides a variable
that is already set.

Live-cluster tests live in tests/integration and are skipped unless
RUN_K8S_INTEGRATION=1 (see docs/kubernetes.md).
"""

import os

os.environ["ENVIRONMENT"] = "simulator"
