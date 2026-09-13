"""Infrastructure adapter for the in-memory simulator.

A thin delegation layer over ``backend.tools.diagnostics`` and
``backend.tools.remediation``. Functions are looked up on those modules at
call time, so the simulator's behaviour (and anything that patches those
tools in tests) is exactly what it was before the abstraction existed.
"""

from typing import Any, Dict, List

from backend.infrastructure.base import Infrastructure
from backend.shared import slo
from backend.tools import diagnostics, remediation


class SimulatorInfrastructure(Infrastructure):
    """The deterministic in-memory simulator."""

    name = "simulator"
    supports_scenario_injection = True

    def describe(self) -> Dict[str, Any]:
        return {
            "environment": self.name,
            "target": "in-memory simulated service",
            "replicas": {"min": slo.MIN_REPLICAS, "max": slo.MAX_REPLICAS},
        }

    def get_metrics(self) -> Dict[str, Any]:
        return diagnostics.get_metrics()

    def check_health(self) -> Dict[str, Any]:
        return diagnostics.check_health()

    def get_current_version(self) -> str:
        return diagnostics.get_current_version()

    def get_capacity(self) -> Dict[str, Any]:
        return diagnostics.get_capacity()

    def query_logs(self) -> List[Dict[str, str]]:
        return diagnostics.query_logs()

    def get_deployment_history(self) -> List[Dict[str, Any]]:
        return diagnostics.get_deployment_history()

    def restart_service(self) -> Dict[str, Any]:
        return remediation.restart_service()

    def rollback_deployment(self, version: str) -> Dict[str, Any]:
        return remediation.rollback_deployment(version)

    def scale_service(self, replicas: int) -> Dict[str, Any]:
        return remediation.scale_service(replicas)
