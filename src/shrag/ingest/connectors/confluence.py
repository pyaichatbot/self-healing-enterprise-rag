from __future__ import annotations

from typing import Any

from shrag.ingest.connectors.base import HTTPConnectorBase


class ConfluenceConnector(HTTPConnectorBase):
    source_type = "confluence"
    required_scopes = ('read:confluence-content',)

    def _discover_path(self, cursor: str | None) -> str:
        suffix = f"&cursor={cursor}" if cursor else ""
        return f"wiki/api/v2/pages?limit={self.config.page_size}{suffix}"

    def _fetch_path(self, object_ref: str) -> str:
        return f"wiki/api/v2/pages/{object_ref}"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            return [f"confluence:page-{i}" for i in range(1, 4)], None
        payload = self._request_json(self._discover_path(cursor))
        results = payload.get("results", [])
        refs = [str(item.get("id")) for item in results if isinstance(item, dict) and item.get("id")]
        next_cursor = payload.get("_links", {}).get("next") if isinstance(payload.get("_links"), dict) else None
        if isinstance(next_cursor, str) and "cursor=" in next_cursor:
            next_cursor = next_cursor.split("cursor=", 1)[1]
        return refs, str(next_cursor) if next_cursor else None

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        refs, next_cursor = self.discover(cursor)
        if self.config.dry_run:
            refs.append("confluence:page-legacy#tombstone")
        return refs, next_cursor

    def fetch(self, object_ref: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "id": object_ref,
                "text": f"Confluence page {object_ref}",
                "updated_at": "2026-05-10T00:00:00Z",
                "acl_groups": ["confluence-users"],
                "version_id": "v2",
            }
        return self._request_json(self._fetch_path(object_ref))
