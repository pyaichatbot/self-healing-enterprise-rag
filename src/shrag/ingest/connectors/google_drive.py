from __future__ import annotations

from typing import Any

from shrag.ingest.connectors.base import HTTPConnectorBase


class GoogleDriveConnector(HTTPConnectorBase):
    source_type = "google_drive"
    required_scopes = ('https://www.googleapis.com/auth/drive.readonly',)

    def _discover_path(self, cursor: str | None) -> str:
        token = f"&pageToken={cursor}" if cursor else ""
        return f"drive/v3/files?pageSize={self.config.page_size}&fields=nextPageToken,files(id,name,mimeType,modifiedTime){token}"

    def _fetch_path(self, object_ref: str) -> str:
        return f"drive/v3/files/{object_ref}?alt=media"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            return [f"gdrive-{i}" for i in range(1, 4)], None
        payload = self._request_json(self._discover_path(cursor))
        files = payload.get("files", [])
        refs = [str(item.get("id")) for item in files if isinstance(item, dict) and item.get("id")]
        next_cursor = payload.get("nextPageToken")
        return refs, str(next_cursor) if next_cursor else None

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        refs, next_cursor = self.discover(cursor)
        if self.config.dry_run:
            refs.append("gdrive-deleted#tombstone")
        return refs, next_cursor

    def fetch(self, object_ref: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {
                "id": object_ref,
                "text": f"Google Drive content for {object_ref}",
                "updated_at": "2026-05-10T00:00:00Z",
                "acl_groups": ["drive-readers"],
                "version_id": "drive-v7",
            }
        return self._request_json(self._fetch_path(object_ref))
