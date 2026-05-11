from __future__ import annotations

from typing import Any
from urllib.parse import quote

from shrag.ingest.connectors.base import HTTPConnectorBase


class GitHubConnector(HTTPConnectorBase):
    source_type = "github"
    required_scopes = ('repo',)

    def _discover_path(self, cursor: str | None) -> str:
        page = cursor or "1"
        return f"repos?per_page={self.config.page_size}&page={page}"

    def _fetch_path(self, object_ref: str) -> str:
        # object_ref format: owner/repo:path@ref
        owner_repo, file_path, ref = self._parse_repo_object_ref(object_ref)
        encoded_path = quote(file_path, safe="/")
        return f"repos/{owner_repo}/contents/{encoded_path}?ref={quote(ref, safe='')}"

    def discover(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if not self.config.dry_run:
            payload = self._request_json(self._discover_path(cursor))
            items = self._extract_items(payload)
            refs: list[str] = []
            for item in items:
                repo = str(item.get("repo") or item.get("full_name") or "").strip()
                file_path = str(item.get("path") or item.get("file_path") or "").strip()
                ref = str(item.get("ref") or item.get("default_branch") or self.config.ref or "main").strip()
                if repo and file_path:
                    filtered = self.filter_repo_paths([file_path])
                    if filtered:
                        refs.append(f"{repo}:{filtered[0]}@{ref}")
            return refs, self._extract_next_cursor(payload)
        ref = self.config.ref or "main"
        repo = "octo-org/platform-rag"
        paths = self.filter_repo_paths(
            [
                "docs/architecture.md",
                "docs/adr/001-indexing.md",
                "src/pipeline.py",
                "src/generated/cache.bin",
            ]
        )
        refs = [f"{repo}:{path}@{ref}" for path in paths]
        return refs, None

    def delta_since(self, cursor: str | None = None) -> tuple[list[str], str | None]:
        if not self.config.dry_run:
            payload = self._request_json(self._discover_path(cursor))
            repo = str(payload.get("repo") or payload.get("full_name") or "").strip()
            ref = str(payload.get("ref") or self.config.ref or "main").strip()
            head_sha = str(payload.get("head_sha") or payload.get("after") or "")
            files = payload.get("files")
            refs: list[str] = []
            if isinstance(files, list):
                for file in files:
                    if not isinstance(file, dict):
                        continue
                    file_path = str(file.get("filename") or file.get("path") or "").strip()
                    if not file_path or not repo:
                        continue
                    filtered = self.filter_repo_paths([file_path])
                    if not filtered:
                        continue
                    status = str(file.get("status") or "")
                    item_ref = f"{repo}:{filtered[0]}@{ref}"
                    if head_sha:
                        item_ref = f"{item_ref}#commit={head_sha}"
                    if status in {"removed", "deleted"}:
                        item_ref = f"{item_ref}#tombstone"
                    refs.append(item_ref)
            next_cursor = head_sha or self._extract_next_cursor(payload)
            return refs, str(next_cursor) if next_cursor else None
        old_sha = cursor or "sha-old"
        new_sha = "sha-new"
        repo = "octo-org/platform-rag"
        ref = self.config.ref or "main"
        changed_paths = self.filter_repo_paths(["docs/architecture.md", "src/retrieve/router.py"])
        refs = [f"{repo}:{path}@{ref}#commit={new_sha}" for path in changed_paths]
        refs.append(f"{repo}:docs/legacy.md@{ref}#tombstone#from={old_sha}#to={new_sha}")
        return refs, new_sha

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        base = super().normalize(raw)
        file_path = str(raw.get("path") or raw.get("file_path") or "")
        if file_path:
            base["metadata"]["file_path"] = file_path
            base["metadata"]["ref"] = str(raw.get("ref") or self.config.ref or "HEAD")
            base["metadata"]["source_url"] = str(raw.get("html_url") or "")
        if raw.get("commit_sha"):
            base["metadata"]["commit_sha"] = str(raw.get("commit_sha"))
        return base

    def fetch(self, object_ref: str) -> dict[str, Any]:
        owner_repo, file_path, ref = self._parse_repo_object_ref(object_ref)
        if self.config.dry_run:
            text = f"GitHub synthetic file {file_path} at {owner_repo}@{ref}"
            return {
                "id": f"github:{owner_repo}:{file_path}@{ref}",
                "path": file_path,
                "text": text,
                "ref": ref,
                "commit_sha": self._extract_commit_sha(object_ref),
                "html_url": f"https://github.com/{owner_repo}/blob/{ref}/{file_path}",
                "acl_groups": ["engineering", "platform"],
            }
        return self._request_json(self._fetch_path(object_ref))

    def _parse_repo_object_ref(self, object_ref: str) -> tuple[str, str, str]:
        left, _, commit_part = object_ref.partition("#commit=")
        _ = commit_part
        path_and_ref = left
        owner_repo, sep, remainder = path_and_ref.partition(":")
        if not sep:
            return object_ref, "README.md", self.config.ref or "main"
        file_path, ref_sep, ref = remainder.partition("@")
        final_ref = ref if ref_sep else (self.config.ref or "main")
        return owner_repo, file_path or "README.md", final_ref

    def _extract_commit_sha(self, object_ref: str) -> str | None:
        marker = "#commit="
        if marker not in object_ref:
            return None
        return object_ref.split(marker, 1)[1].split("#", 1)[0] or None
