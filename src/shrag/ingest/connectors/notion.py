from __future__ import annotations

from typing import Any

from shrag.ingest.connectors.base import HTTPConnectorBase


class NotionConnector(HTTPConnectorBase):
    source_type = "notion"
    required_scopes = ('read:content',)

    def _discover_path(self, cursor: str | None) -> str:
        # Notion discovery typically requires POST search; mapped to endpoint path for base client.
        _ = cursor
        return "v1/search"

    def _fetch_path(self, object_ref: str) -> str:
        return f"v1/blocks/{object_ref}/children"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            return [f"notion-page-{i}" for i in range(1, 4)], None
        payload = self._request_json(self._discover_path(cursor))
        results = payload.get("results", [])
        refs = [str(item.get("id")) for item in results if isinstance(item, dict) and item.get("id")]
        next_cursor = payload.get("next_cursor")
        return refs, str(next_cursor) if next_cursor else None

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        refs, next_cursor = self.discover(cursor)
        if self.config.dry_run:
            refs.append("notion-page-legacy#tombstone")
        return refs, next_cursor

    def fetch(self, object_ref: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "id": object_ref,
                "text": f"Notion page {object_ref}",
                "updated_at": "2026-05-10T00:00:00Z",
                "acl_groups": ["notion-workspace"],
                "version_id": "notion-v3",
            }
        return self._request_json(self._fetch_path(object_ref))
