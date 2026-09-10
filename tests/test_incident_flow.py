from fastapi.testclient import TestClient

from simulator.service import app


client = TestClient(app)


def test_bad_deployment_incident():

    # 1. Inject incident
    response = client.post("/simulate/outage")

    assert response.status_code == 200

    # 2. Verify that the service is actually unhealthy
    health = client.get("/health")

    assert health.status_code == 200
    assert health.json()["status"] == "down"

    # 3. Verify incident metrics
    metrics = client.get("/metrics")

    assert metrics.status_code == 200

    data = metrics.json()

    assert data["error_rate"] == 0.70
    assert data["latency_ms"] == 1000