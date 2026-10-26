"""Versioned, JSON-serializable state for one scheduled execution."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def new_run_manifest(run_id: str | None = None, *, previous_revision: int = 0) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "run_id": run_id or str(uuid4()),
        "status": "running",
        "started_at": now,
        "completed_at": None,
        "manifest_revision": previous_revision,
        "inventory_complete": False,
        "inventory": {},
        "resources": [],
        "stages": {},
        "assessment_counts": {},
        "run_duration_seconds": None,
        "priced_exposure_monthly": {"currency": "USD", "amount": None, "priced_count": 0, "unpriced_count": 0},
        "delivery": {"status": "not_started", "report_path": None, "attempts": 0},
        "errors": [],
    }


def snapshot(manifest: dict) -> dict:
    manifest["manifest_revision"] += 1
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    return manifest
