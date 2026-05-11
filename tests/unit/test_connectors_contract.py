from shrag.ingest.connectors import ConnectorConfig, resolve_connector
from shrag.ingest.connectors.base import HTTPConnectorBase


SOURCES = [
    "confluence",
    "jira",
    "sharepoint",
    "google_drive",
    "notion",
    "github",
    "gitlab",
    "webdav_s3",
]


def test_all_connectors_implement_contract_methods():
    for source in SOURCES:
        connector = resolve_connector(source, ConnectorConfig(base_url="https://example.invalid", token="t", dry_run=True))
        scope_map = {
            "confluence": "read:confluence-content",
            "jira": "read:jira-work",
            "sharepoint": "Files.Read.All",
            "google_drive": "https://www.googleapis.com/auth/drive.readonly",
            "notion": "read:content",
            "github": "repo",
            "gitlab": "read_api",
            "webdav_s3": "read:objects",
        }
        assert connector.authenticate({"token": "t", "scopes": scope_map[source]}) is True
        refs, cursor = connector.discover()
        assert isinstance(refs, list)
        assert cursor is None
        payload = connector.fetch(refs[0] if refs else f"{source}:1")
        normalized = connector.normalize(payload)
        assert normalized["document_id"]
        assert "text" in normalized
        assert normalized["metadata"]["source_type"] == source
        assert normalized["metadata"]["source_id"]
        assert normalized["metadata"]["version_id"]


def test_repo_path_filtering_respects_globs_and_extension_allowlist():
    connector = HTTPConnectorBase(
        ConnectorConfig(
            base_url="https://example.invalid",
            dry_run=True,
            include_globs=("docs/**", "src/**"),
            exclude_globs=("**/generated/**",),
            allowed_extensions=(".md", ".py"),
        )
    )
    paths = [
        "docs/guide.md",
        "docs/spec.txt",
        "src/app.py",
        "src/generated/schema.py",
        "assets/logo.png",
    ]
    assert connector.filter_repo_paths(paths) == ["docs/guide.md", "src/app.py"]


def test_delta_marks_tombstones_in_dry_run():
    connector = resolve_connector("confluence", ConnectorConfig(base_url="https://example.invalid", token="t", dry_run=True))
    refs, cursor = connector.delta_since("cursor-1")
    assert cursor is None
    assert refs
    assert any(ref.endswith("#tombstone") for ref in refs)
    assert any(ref.startswith("confluence:") for ref in refs)


def test_authentication_fails_when_required_scope_missing():
    connector = resolve_connector("github", ConnectorConfig(base_url="https://api.github.com", token="t", dry_run=True))
    assert connector.authenticate({"token": "t", "scopes": "read:org"}) is False
