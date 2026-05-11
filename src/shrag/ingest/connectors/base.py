from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

import httpx


class Connector(Protocol):
    def authenticate(self, config: dict[str, str]) -> bool: ...
    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]: ...
    def fetch(self, object_ref: str) -> dict[str, Any]: ...
    def checkpoint(self) -> str | None: ...
    def resume(self, checkpoint: str | None) -> None: ...
    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]: ...
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(slots=True)
class ConnectorConfig:
    base_url: str
    token: str | None = None
    page_size: int = 50
    dry_run: bool = True
    # Optional repository-oriented controls for source connectors.
    ref: str | None = None
    include_globs: tuple[str, ...] = ("**",)
    exclude_globs: tuple[str, ...] = (
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/.git/**",
        "**/.cache/**",
    )
    allowed_extensions: tuple[str, ...] = ()
    max_retries: int = 3
    retry_backoff_seconds: float = 0.25


class HTTPConnectorBase:
    """Reusable base class for enterprise source connectors."""

    source_type = "generic"
    required_scopes: tuple[str, ...] = ()

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._cursor: str | None = None
        self._headers = {"Authorization": f"Bearer {config.token}"} if config.token else {}

    def authenticate(self, config: dict[str, str]) -> bool:
        token = config.get("token") or self.config.token
        if not (token and token.strip()):
            return False
        return self._has_required_scopes(config)

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            page = [f"{self.source_type}:{i}" for i in range(1, 6)]
            return page, None
        payload = self._request_json(self._discover_path(cursor))
        items = self._extract_items(payload)
        refs = [self._extract_ref(item) for item in items]
        refs = [ref for ref in refs if ref]
        return refs, self._extract_next_cursor(payload)

    def fetch(self, object_ref: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {"id": object_ref, "text": f"Synthetic content for {object_ref}", "metadata": {"source_type": self.source_type}}
        return self._request_json(self._fetch_path(object_ref))

    def checkpoint(self) -> str | None:
        return self._cursor

    def resume(self, checkpoint: str | None) -> None:
        self._cursor = checkpoint

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if self.config.dry_run:
            delta_refs = [f"{self.source_type}:delta:1", f"{self.source_type}:delta:2"]
            return delta_refs, None
        payload = self._request_json(self._discover_path(cursor))
        items = self._extract_items(payload)
        refs: list[str] = []
        for item in items:
            ref = self._extract_ref(item)
            if not ref:
                continue
            if bool(item.get("deleted") or item.get("is_deleted")):
                refs.append(f"{ref}#tombstone")
            else:
                refs.append(ref)
        return refs, self._extract_next_cursor(payload)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        source_id = str(raw.get("id") or raw.get("source_id") or raw.get("document_id") or "unknown")
        version_id = str(raw.get("version_id") or raw.get("etag") or raw.get("sha") or raw.get("updated_at") or "v1")
        acl_groups_raw = raw.get("acl_groups") or raw.get("principal_groups") or []
        if isinstance(acl_groups_raw, str):
            acl_groups = [group.strip() for group in acl_groups_raw.split(",") if group.strip()]
        else:
            acl_groups = [str(group).strip() for group in acl_groups_raw if str(group).strip()]
        return {
            "document_id": source_id,
            "text": str(raw.get("text") or raw.get("content") or ""),
            "metadata": {
                **(raw.get("metadata") or {}),
                "source_type": self.source_type,
                "source_id": source_id,
                "version_id": version_id,
                "updated_at": raw.get("updated_at") or raw.get("modified_time"),
                "acl_groups": tuple(sorted(set(acl_groups))),
            },
        }

    def filter_repo_paths(self, paths: list[str]) -> list[str]:
        """Filter source file paths by include/exclude globs and extension allowlist."""
        allow = {ext.lower() for ext in self.config.allowed_extensions}
        filtered: list[str] = []
        for path in paths:
            posix = path.strip().lstrip("/")
            if not posix:
                continue
            if not any(fnmatch(posix, pattern) for pattern in self.config.include_globs):
                continue
            if any(fnmatch(posix, pattern) for pattern in self.config.exclude_globs):
                continue
            if allow:
                ext = PurePosixPath(posix).suffix.lower()
                if ext and ext not in allow:
                    continue
            filtered.append(posix)
        return filtered

    def _discover_path(self, cursor: str | None) -> str:
        raise NotImplementedError

    def _fetch_path(self, object_ref: str) -> str:
        raise NotImplementedError

    def _request_json(self, path: str) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                with httpx.Client(timeout=15.0) as client:
                    response = client.get(url, headers=self._headers)
                    response.raise_for_status()
                    payload = response.json()
                    if isinstance(payload, dict):
                        return payload
                    return {"items": payload}
            except Exception as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
        if last_error is not None:
            raise last_error
        return {"items": []}

    def _extract_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("items", "results", "files", "value"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _extract_ref(self, item: dict[str, Any]) -> str:
        value = item.get("id") or item.get("key") or item.get("path") or item.get("object_ref")
        return str(value) if value is not None else ""

    def _extract_next_cursor(self, payload: dict[str, Any]) -> str | None:
        direct = payload.get("next_cursor") or payload.get("nextPageToken") or payload.get("cursor")
        if direct:
            return str(direct)
        next_link = payload.get("_links", {}).get("next") if isinstance(payload.get("_links"), dict) else None
        if isinstance(next_link, str):
            parsed = urlparse(next_link)
            params = parse_qs(parsed.query)
            for key in ("cursor", "pageToken", "startAt", "offset", "skip"):
                values = params.get(key)
                if values:
                    return values[0]
        return None

    def _has_required_scopes(self, config: dict[str, str]) -> bool:
        if not self.required_scopes:
            return True
        scopes_raw = config.get("scopes", "")
        provided = {scope.strip() for scope in scopes_raw.split(",") if scope.strip()}
        return all(scope in provided for scope in self.required_scopes)
