from ops.verification.connector_evidence import ConnectorCheckInput, run_connector_evidence


class _FakeConnector:
    def __init__(self, auth_ok: bool = True):
        self._auth_ok = auth_ok

    def authenticate(self, config):
        _ = config
        return self._auth_ok

    def discover(self, cursor=None):
        _ = cursor
        return ["ref-1"], None


def test_connector_evidence_skips_disabled():
    checks = (ConnectorCheckInput(source="github", base_url=None, token=None, scopes=None, enabled=False),)
    report = run_connector_evidence(checks, resolver=lambda s, c: _FakeConnector())
    assert report.passed is True
    assert report.results[0].status == "skip"
    assert report.skipped_count == 1


def test_connector_evidence_fails_on_auth_scope_failure():
    checks = (ConnectorCheckInput(source="github", base_url="https://api.github.com", token="t", scopes="read:org", enabled=True),)
    report = run_connector_evidence(checks, resolver=lambda s, c: _FakeConnector(auth_ok=False))
    assert report.passed is False
    assert report.results[0].status == "fail"
    assert report.results[0].reason == "auth_scope_failed"


def test_connector_evidence_strict_mode_fails_when_skipped():
    checks = (ConnectorCheckInput(source="github", base_url=None, token=None, scopes=None, enabled=False),)
    report = run_connector_evidence(checks, require_no_skips=True, resolver=lambda s, c: _FakeConnector())
    assert report.passed is False
    assert report.strict_required is True


def test_connector_evidence_requires_minimum_passes():
    checks = (ConnectorCheckInput(source="github", base_url="https://api.github.com", token="t", scopes="repo", enabled=True),)
    report = run_connector_evidence(checks, min_passed=2, resolver=lambda s, c: _FakeConnector())
    assert report.passed is False
    assert report.passed_count == 1
