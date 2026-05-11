# Connectors

## Objective
Provide a strict connector SDK contract so new sources can be integrated without changing ingest core logic.

## Required Connector Contract
Every connector must implement:
- `authenticate(config)`: verify credentials and minimum scopes.
- `discover(cursor)`: paginated object discovery.
- `fetch(object_ref)`: content + metadata retrieval.
- `checkpoint()/resume(checkpoint)`: resumable sync.
- `delta_since(cursor)`: incremental updates/deletes.
- `normalize(raw)`: canonical document schema mapping.

Canonical identity contract:
- `source_type`
- `source_id` (stable external object id)
- `version_id` (source version/etag/commit)
- `tenant_id`
- `updated_at`

## Enterprise Acceptance Criteria
- Supports provider pagination and bounded retries with jitter.
- Preserves tombstones/deletes via `delta_since`.
- Emits ACL principal/group metadata for retrieval-time authorization filtering.
- Supports idempotent replay: same `source_id+version_id` must not duplicate chunks.
- Emits connector labels for observability: `source_type`, `connector_version`, `tenant_id`.

## Supported Enterprise Sources
- Collaboration/work management: Confluence, Jira, Notion.
- Document systems: SharePoint, Google Drive.
- Engineering knowledge: GitHub, GitLab.
- File stores: WebDAV/S3-style stores.

## GitHub/GitLab Repository Ingestion Policy
Required controls:
- `ref` selection: branch, tag, or pinned commit SHA.
- `include_globs` / `exclude_globs`.
- `allowed_extensions` for strict allowlist operation.

Default allowlist:
- `.md`, `.mdx`, `.rst`, `.txt`, `.adoc`, `.html`, `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.csv`, `.sql`
- `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.kt`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.hpp`, `.cs`, `.rb`, `.php`, `.scala`, `.swift`, `.sh`

Default blocklist:
- Binary/media artifacts and generated dirs: `node_modules`, `dist`, `build`, caches.

## Attachment Ingestion Requirements
- Parse: PDF, DOCX, PPTX, XLSX, TXT, HTML, Markdown.
- Preserve lineage: parent object -> attachment -> extracted chunks.
- Propagate ACL context from parent and attachment metadata.
- Enforce file size/type guardrails before parsing.
