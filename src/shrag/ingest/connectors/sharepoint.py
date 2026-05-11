from __future__ import annotations

from typing import Any

from shrag.ingest.connectors.base import HTTPConnectorBase


class SharePointConnector(HTTPConnectorBase):
    source_type = "sharepoint"
    required_scopes = ('Files.Read.All',)

    def _discover_path(self, cursor: str | None) -> str:
        skip = cursor or "0"
        return f"v1.0/sites/root/drive/root/children?$top={self.config.page_size}&$skip={skip}"

    def _fetch_path(self, object_ref: str) -> str:
        return f"v1.0/drives/{object_ref}"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            return [f"sp-doc-{i}" for i in range(1, 4)], None
        payload = self._request_json(self._discover_path(cursor))
        value = payload.get("value", [])
        refs = [str(item.get("id")) for item in value if isinstance(item, dict) and item.get("id")]
        next_link = payload.get("@odata.nextLink")
        if isinstance(next_link, str) and "$skip=" in next_link:
            return refs, next_link.split("$skip=", 1)[1]
        return refs, None

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        refs, next_cursor = self.discover(cursor)
        if self.config.dry_run:
            refs.append("sp-doc-deleted#tombstone")
        return refs, next_cursor

    def fetch(self, object_ref: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "id": object_ref,
                "text": f"SharePoint document {object_ref}",
                "updated_at": "2026-05-10T00:00:00Z",
                "acl_groups": ["sharepoint-members"],
                "version_id": "sp-v1",
            }
        return self._request_json(self._fetch_path(object_ref))
