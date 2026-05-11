from shrag.observe.ha import evaluate_ha_readiness


def test_primary_region_ready_when_healthy():
    status = evaluate_ha_readiness(
        region="eu-primary",
        mode="active-passive",
        primary_region="eu-primary",
        primary_region_healthy=True,
        replication_lag_seconds=0,
        max_replication_lag_seconds=900,
    )
    assert status.ready is True
    assert status.role == "primary"


def test_secondary_serves_on_failover_when_lag_within_limit():
    status = evaluate_ha_readiness(
        region="us-secondary",
        mode="active-passive",
        primary_region="eu-primary",
        primary_region_healthy=False,
        replication_lag_seconds=120,
        max_replication_lag_seconds=900,
    )
    assert status.ready is True
    assert status.reason == "failover_serving"


def test_secondary_not_ready_with_excessive_replication_lag():
    status = evaluate_ha_readiness(
        region="us-secondary",
        mode="active-passive",
        primary_region="eu-primary",
        primary_region_healthy=False,
        replication_lag_seconds=1900,
        max_replication_lag_seconds=900,
    )
    assert status.ready is False
    assert status.reason == "replication_lag_exceeded"
