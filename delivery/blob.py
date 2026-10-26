"""Immutable run artifacts in Azure Blob Storage."""

from __future__ import annotations

import json
import os

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


def _container_client():
    container = os.getenv("REPORT_CONTAINER", "waste-reports")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    if account_url:
        service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
    else:
        connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL is not set")
        service = BlobServiceClient.from_connection_string(connection)
    return service.get_container_client(container)


def archive_report(run_id: str, report: str) -> str:
    """Create a run-specific report object; never overwrite a prior report."""
    name = f"runs/{run_id}/report.md"
    _container_client().upload_blob(name, report, overwrite=False,
                                    content_settings=ContentSettings(content_type="text/markdown"))
    return name


def archive_manifest(manifest: dict) -> str:
    """Append one immutable manifest snapshot for a run."""
    run_id = manifest["run_id"]
    revision = manifest["manifest_revision"]
    name = f"runs/{run_id}/manifests/{revision:04d}.json"
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    _container_client().upload_blob(name, payload, overwrite=False,
                                    content_settings=ContentSettings(content_type="application/json"))
    return name


def load_latest_manifest(run_id: str) -> dict | None:
    """Load the latest immutable checkpoint for one scheduled run."""
    container = _container_client()
    prefix = f"runs/{run_id}/manifests/"
    names = sorted(blob.name for blob in container.list_blobs(name_starts_with=prefix) if blob.name.endswith(".json"))
    if not names:
        return None
    payload = container.download_blob(names[-1]).readall()
    return json.loads(payload)
