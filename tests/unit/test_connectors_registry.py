from shrag.ingest.connectors import ConnectorConfig, resolve_connector
from shrag.ingest.connectors.confluence import ConfluenceConnector
from shrag.ingest.connectors.github import GitHubConnector
from shrag.ingest.connectors.google_drive import GoogleDriveConnector
from shrag.ingest.connectors.jira import JiraConnector
from shrag.ingest.connectors.gitlab import GitLabConnector
from shrag.ingest.connectors.notion import NotionConnector
from shrag.ingest.connectors.sharepoint import SharePointConnector


def test_connector_registry_returns_github_connector():
    connector = resolve_connector(
        "github",
        ConnectorConfig(
            base_url="https://api.github.com",
            token="x",
            dry_run=True,
            ref="main",
            include_globs=("docs/**", "src/**"),
            allowed_extensions=(".md", ".py"),
        ),
    )
    refs, next_cursor = connector.discover()
    assert refs
    assert all("@" in ref for ref in refs)
    assert all(":docs/" in ref or ":src/" in ref for ref in refs)
    assert next_cursor is None


def test_connector_normalize_contract():
    connector = resolve_connector(
        "gitlab",
        ConnectorConfig(base_url="https://gitlab.example.com", token="x", dry_run=True),
    )
    raw = connector.fetch("proj-1")
    normalized = connector.normalize(raw)
    assert normalized["document_id"]
    assert isinstance(normalized["text"], str)
    assert normalized["metadata"]["source_type"] == "gitlab"


def test_github_delta_contains_commit_cursor_and_tombstone():
    connector = resolve_connector(
        "github",
        ConnectorConfig(base_url="https://api.github.com", token="x", dry_run=True, ref="main"),
    )
    refs, next_cursor = connector.delta_since("sha-prev")
    assert next_cursor == "sha-new"
    assert any("#commit=sha-new" in ref for ref in refs)
    assert any("#tombstone" in ref for ref in refs)


def test_gitlab_fetch_parses_structured_object_ref():
    connector = resolve_connector(
        "gitlab",
        ConnectorConfig(base_url="https://gitlab.example.com", token="x", dry_run=True, ref="main"),
    )
    payload = connector.fetch("platform/rag-service:docs/runbook.md@main#commit=abc123")
    normalized = connector.normalize(payload)
    assert normalized["metadata"]["file_path"] == "docs/runbook.md"
    assert normalized["metadata"]["ref"] == "main"
    assert normalized["metadata"]["commit_sha"] == "abc123"


def test_github_non_dry_discover_parses_provider_payload(monkeypatch):
    connector = GitHubConnector(
        ConnectorConfig(
            base_url="https://api.github.com",
            token="x",
            dry_run=False,
            include_globs=("docs/**",),
            allowed_extensions=(".md",),
        )
    )

    def fake_request_json(path: str):
        _ = path
        return {
            "items": [
                {"repo": "octo-org/rag", "path": "docs/architecture.md", "default_branch": "main"},
                {"repo": "octo-org/rag", "path": "src/main.py", "default_branch": "main"},
            ],
            "next_cursor": "2",
        }

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.discover("1")
    assert refs == ["octo-org/rag:docs/architecture.md@main"]
    assert cursor == "2"


def test_gitlab_non_dry_delta_parses_changes_and_tombstones(monkeypatch):
    connector = GitLabConnector(
        ConnectorConfig(
            base_url="https://gitlab.example.com",
            token="x",
            dry_run=False,
            include_globs=("docs/**",),
            allowed_extensions=(".md",),
        )
    )

    def fake_request_json(path: str):
        _ = path
        return {
            "project_path_with_namespace": "platform/rag",
            "ref": "main",
            "head_sha": "sha-2",
            "changes": [
                {"new_path": "docs/runbook.md", "deleted_file": False},
                {"old_path": "docs/legacy.md", "new_path": "docs/legacy.md", "deleted_file": True},
                {"new_path": "src/engine.py", "deleted_file": False},
            ],
        }

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.delta_since("sha-1")
    assert "platform/rag:docs/runbook.md@main#commit=sha-2" in refs
    assert "platform/rag:docs/legacy.md@main#commit=sha-2#tombstone" in refs
    assert all(":src/" not in ref for ref in refs)
    assert cursor == "sha-2"


def test_confluence_non_dry_discover_reads_results_payload(monkeypatch):
    connector = ConfluenceConnector(ConnectorConfig(base_url="https://conf.example.com", token="x", dry_run=False))

    def fake_request_json(path: str):
        _ = path
        return {"results": [{"id": "123"}, {"id": "456"}], "_links": {"next": "/wiki/api/v2/pages?cursor=abc"}}

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.discover()
    assert refs == ["123", "456"]
    assert cursor == "abc"


def test_jira_non_dry_discover_uses_issue_keys(monkeypatch):
    connector = JiraConnector(ConnectorConfig(base_url="https://jira.example.com", token="x", dry_run=False))

    def fake_request_json(path: str):
        _ = path
        return {"issues": [{"key": "ENG-1"}, {"key": "ENG-2"}], "startAt": 0, "maxResults": 2, "total": 5}

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.discover("0")
    assert refs == ["ENG-1", "ENG-2"]
    assert cursor == "2"


def test_sharepoint_non_dry_discover_parses_next_skip(monkeypatch):
    connector = SharePointConnector(ConnectorConfig(base_url="https://sp.example.com", token="x", dry_run=False))

    def fake_request_json(path: str):
        _ = path
        return {
            "value": [{"id": "doc-1"}, {"id": "doc-2"}],
            "@odata.nextLink": "https://sp.example.com/drive?$skip=200",
        }

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.discover("0")
    assert refs == ["doc-1", "doc-2"]
    assert cursor == "200"


def test_notion_non_dry_discover_uses_next_cursor(monkeypatch):
    connector = NotionConnector(ConnectorConfig(base_url="https://notion.example.com", token="x", dry_run=False))

    def fake_request_json(path: str):
        _ = path
        return {"results": [{"id": "page-a"}], "next_cursor": "next-1"}

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.discover(None)
    assert refs == ["page-a"]
    assert cursor == "next-1"


def test_gdrive_non_dry_discover_uses_page_token(monkeypatch):
    connector = GoogleDriveConnector(ConnectorConfig(base_url="https://drive.google.com", token="x", dry_run=False))

    def fake_request_json(path: str):
        _ = path
        return {"files": [{"id": "file-a"}, {"id": "file-b"}], "nextPageToken": "tok-2"}

    monkeypatch.setattr(connector, "_request_json", fake_request_json)
    refs, cursor = connector.discover(None)
    assert refs == ["file-a", "file-b"]
    assert cursor == "tok-2"
