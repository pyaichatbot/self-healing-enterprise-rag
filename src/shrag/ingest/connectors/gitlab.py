from __future__ import annotations

from typing import Any
from urllib.parse import quote

from shrag.ingest.connectors.base import HTTPConnectorBase


class GitLabConnector(HTTPConnectorBase):
    source_type = "gitlab"
    required_scopes = ('read_api',)

    def _discover_path(self, cursor: str | None) -> str:
        page = cursor or "1"
        return f"api/v4/projects?per_page={self.config.page_size}&page={page}"

    def _fetch_path(self, object_ref: str) -> str:
        # object_ref format: namespace/project:path@ref
        project, file_path, ref = self._parse_repo_object_ref(object_ref)
        project_encoded = quote(project, safe="")
        file_encoded = quote(file_path, safe="")
        ref_encoded = quote(ref, safe="")
        return f"api/v4/projects/{project_encoded}/repository/files/{file_encoded}?ref={ref_encoded}"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if not self.config.dry_run:
            payload = self._request_json(self._discover_path(cursor))
            items = self._extract_items(payload)
            refs: list[str] = []
            for item in items:
                project = str(item.get("project_path_with_namespace") or item.get("project") or "").strip()
                file_path = str(item.get("path") or item.get("file_path") or "").strip()
                ref = str(item.get("ref") or item.get("default_branch") or self.config.ref or "main").strip()
                if project and file_path:
                    filtered = self.filter_repo_paths([file_path])
                    if filtered:
                        refs.append(f"{project}:{filtered[0]}@{ref}")
            return refs, self._extract_next_cursor(payload)
        ref = self.config.ref or "main"
        project = "platform/rag-service"
        paths = self.filter_repo_paths(
            [
                "README.md",
                "docs/runbook.md",
                "src/engine.py",
                "dist/artifact.js",
            ]
        )
        refs = [f"{project}:{path}@{ref}" for path in paths]
        return refs, None

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if not self.config.dry_run:
            payload = self._request_json(self._discover_path(cursor))
            project = str(payload.get("project_path_with_namespace") or payload.get("project") or "").strip()
            ref = str(payload.get("ref") or self.config.ref or "main").strip()
            head_sha = str(payload.get("head_sha") or payload.get("to") or "")
            refs: list[str] = []
            changes = payload.get("changes")
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    file_path = str(change.get("new_path") or change.get("old_path") or "").strip()
                    if not file_path or not project:
                        continue
                    filtered = self.filter_repo_paths([file_path])
                    if not filtered:
                        continue
                    deleted = bool(change.get("deleted_file"))
                    item_ref = f"{project}:{filtered[0]}@{ref}"
                    if head_sha:
                        item_ref = f"{item_ref}#commit={head_sha}"
                    if deleted:
                        item_ref = f"{item_ref}#tombstone"
                    refs.append(item_ref)
            next_cursor = head_sha or self._extract_next_cursor(payload)
            return refs, str(next_cursor) if next_cursor else None
        old_sha = cursor or "commit-old"
        new_sha = "commit-new"
        project = "platform/rag-service"
        ref = self.config.ref or "main"
        changed_paths = self.filter_repo_paths(["docs/runbook.md", "src/retrieve/hybrid.py"])
        refs = [f"{project}:{path}@{ref}#commit={new_sha}" for path in changed_paths]
        refs.append(f"{project}:docs/obsolete.md@{ref}#tombstone#from={old_sha}#to={new_sha}")
        return refs, new_sha

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        base = super().normalize(raw)
        file_path = str(raw.get("path") or raw.get("file_path") or "")
        if file_path:
            base["metadata"]["file_path"] = file_path
            base["metadata"]["ref"] = str(raw.get("ref") or self.config.ref or "HEAD")
            base["metadata"]["source_url"] = str(raw.get("web_url") or "")
        if raw.get("commit_sha"):
            base["metadata"]["commit_sha"] = str(raw.get("commit_sha"))
        return base

    def fetch(self, object_ref: str) -> dict[str, Any]:
        project, file_path, ref = self._parse_repo_object_ref(object_ref)
        if self.config.dry_run:
            return {
                "id": f"gitlab:{project}:{file_path}@{ref}",
                "path": file_path,
                "text": f"GitLab synthetic file {file_path} at {project}@{ref}",
                "ref": ref,
                "commit_sha": self._extract_commit_sha(object_ref),
                "web_url": f"https://gitlab.example.com/{project}/-/blob/{ref}/{file_path}",
                "acl_groups": ["engineering", "platform"],
            }
        return self._request_json(self._fetch_path(object_ref))

    def _parse_repo_object_ref(self, object_ref: str) -> tuple[str, str, str]:
        left, _, commit_part = object_ref.partition("#commit=")
        _ = commit_part
        project, sep, remainder = left.partition(":")
        if not sep:
            return object_ref, "README.md", self.config.ref or "main"
        file_path, ref_sep, ref = remainder.partition("@")
        final_ref = ref if ref_sep else (self.config.ref or "main")
        return project, file_path or "README.md", final_ref

    def _extract_commit_sha(self, object_ref: str) -> str | None:
        marker = "#commit="
        if marker not in object_ref:
            return None
        return object_ref.split(marker, 1)[1].split("#", 1)[0] or None
