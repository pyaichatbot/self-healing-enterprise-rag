from __future__ import annotations

from shrag.ingest.connectors.base import Connector, ConnectorConfig
from shrag.ingest.connectors.confluence import ConfluenceConnector
from shrag.ingest.connectors.github import GitHubConnector
from shrag.ingest.connectors.gitlab import GitLabConnector
from shrag.ingest.connectors.google_drive import GoogleDriveConnector
from shrag.ingest.connectors.jira import JiraConnector
from shrag.ingest.connectors.notion import NotionConnector
from shrag.ingest.connectors.sharepoint import SharePointConnector
from shrag.ingest.connectors.webdav_s3 import WebDavS3Connector

def resolve_connector(source_type: str, config: ConnectorConfig) -> Connector:
    key = source_type.lower().strip()
    mapping = {
        "confluence": ConfluenceConnector,
        "jira": JiraConnector,
        "sharepoint": SharePointConnector,
        "google_drive": GoogleDriveConnector,
        "notion": NotionConnector,
        "github": GitHubConnector,
        "gitlab": GitLabConnector,
        "webdav_s3": WebDavS3Connector,
    }
    connector_cls = mapping.get(key)
    if connector_cls is None:
        raise ValueError(f"Unsupported connector source_type={source_type}")
    return connector_cls(config)
