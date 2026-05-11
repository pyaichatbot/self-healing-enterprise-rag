from __future__ import annotations

from typing import Any

from shrag.ingest.connectors.base import HTTPConnectorBase


class JiraConnector(HTTPConnectorBase):
    source_type = "jira"
    required_scopes = ('read:jira-work',)

    def _discover_path(self, cursor: str | None) -> str:
        start_at = cursor or "0"
        return f"rest/api/3/search?jql=order+by+updated+desc&maxResults={self.config.page_size}&startAt={start_at}"

    def _fetch_path(self, object_ref: str) -> str:
        return f"rest/api/3/issue/{object_ref}"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            return [f"JRA-{i}" for i in range(100, 103)], None
        payload = self._request_json(self._discover_path(cursor))
        issues = payload.get("issues", [])
        refs = [str(issue.get("key")) for issue in issues if isinstance(issue, dict) and issue.get("key")]
        start_at = int(payload.get("startAt", 0))
        max_results = int(payload.get("maxResults", self.config.page_size))
        total = int(payload.get("total", len(refs)))
        next_cursor = str(start_at + max_results) if (start_at + max_results) < total else None
        return refs, next_cursor

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        refs, next_cursor = self.discover(cursor)
        if self.config.dry_run:
            refs.append("JRA-OLD#tombstone")
        return refs, next_cursor

    def fetch(self, object_ref: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "id": object_ref,
                "text": f"Jira issue {object_ref} with discussion",
                "updated_at": "2026-05-10T00:00:00Z",
                "acl_groups": ["jira-users"],
                "version_id": "issue-v5",
            }
        return self._request_json(self._fetch_path(object_ref))
