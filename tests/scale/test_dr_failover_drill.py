from ops.drills.failover_drill import FailoverDrillInput, evaluate_drill


def test_dr_drill_passes_when_rto_rpo_and_health_targets_are_met():
    report = evaluate_drill(
        FailoverDrillInput(
            rto_target_seconds=3600,
            rpo_target_seconds=900,
            observed_recovery_seconds=600,
            observed_data_loss_seconds=120,
            rollback_verified=True,
            readyz_healthy_after_cutover=True,
        )
    )
    assert report.passed is True
    assert report.reason == "pass"


def test_dr_drill_fails_on_rto_breach():
    report = evaluate_drill(
        FailoverDrillInput(
            rto_target_seconds=600,
            rpo_target_seconds=900,
            observed_recovery_seconds=1200,
            observed_data_loss_seconds=120,
            rollback_verified=True,
            readyz_healthy_after_cutover=True,
        )
    )
    assert report.passed is False
    assert report.reason == "rto_breach"
