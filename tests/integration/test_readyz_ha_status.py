from fastapi.testclient import TestClient

from shrag.app import app
from shrag.settings import settings


client = TestClient(app)


def test_readyz_reports_failover_serving_when_primary_down_and_lag_ok():
    original = (
        settings.region,
        settings.ha_mode,
        settings.primary_region,
        settings.primary_region_healthy,
        settings.replication_lag_seconds,
        settings.max_replication_lag_seconds,
    )
    try:
        settings.region = "us-secondary"
        settings.ha_mode = "active-passive"
        settings.primary_region = "eu-primary"
        settings.primary_region_healthy = False
        settings.replication_lag_seconds = 120
        settings.max_replication_lag_seconds = 900

        response = client.get("/readyz")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["checks"]["ha_reason"] == "failover_serving"
        assert payload["checks"]["ha_role"] == "secondary"
    finally:
        (
            settings.region,
            settings.ha_mode,
            settings.primary_region,
            settings.primary_region_healthy,
            settings.replication_lag_seconds,
            settings.max_replication_lag_seconds,
        ) = original
