from __future__ import annotations

from shrag.ingest.connectors.base import HTTPConnectorBase


class WebDavS3Connector(HTTPConnectorBase):
    source_type = "webdav_s3"
    required_scopes = ('read:objects',)

    def _discover_path(self, cursor: str | None) -> str:
        marker = f"&marker={cursor}" if cursor else ""
        return f"?list-type=2&max-keys={self.config.page_size}{marker}"

    def _fetch_path(self, object_ref: str) -> str:
        return object_ref
