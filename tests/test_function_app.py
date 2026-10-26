from copy import deepcopy
from types import SimpleNamespace

import function_app


def _install_common(monkeypatch, scans=None):
    scans = scans or {}
    monkeypatch.setattr(function_app, "scan_vms", scans.get("vm", lambda: []))
    monkeypatch.setattr(function_app, "scan_unattached_disks", scans.get("disk", lambda: []))
    monkeypatch.setattr(function_app, "scan_load_balancers", scans.get("lb", lambda: []))
    monkeypatch.setattr(function_app, "scan_databases", scans.get("postgres", lambda: []))
    monkeypatch.setattr(function_app, "archive_manifest", lambda manifest: None)
    monkeypatch.setattr(function_app, "load_latest_manifest", lambda run_id: None)
    monkeypatch.setattr(function_app, "archive_report", lambda run_id, report: f"runs/{run_id}/report.md")
    monkeypatch.setattr(function_app, "send_report", lambda report, run_id: {"status": "accepted", "http_status": 202})


def test_empty_complete_run_has_unique_id_and_final_publication(monkeypatch):
    _install_common(monkeypatch)
    first = function_app.waste_hunter(None)
    second = function_app.waste_hunter(None)
    assert first["status"] == "complete"
    assert first["inventory_complete"] is True
    assert first["delivery"]["status"] == "accepted"
    assert first["run_id"] != second["run_id"]
    assert first["priced_exposure_monthly"]["amount"] == 0


def test_partial_scan_is_visible_and_does_not_claim_complete(monkeypatch):
    def broken_scan():
        raise PermissionError("forbidden")

    _install_common(monkeypatch, {"vm": broken_scan})
    result = function_app.waste_hunter(None)
    assert result["status"] == "partial"
    assert result["inventory_complete"] is False
    assert result["errors"][0]["category"] == "unknown"


def test_notification_is_not_sent_before_report_archive(monkeypatch):
    calls = []
    _install_common(monkeypatch)
    monkeypatch.setattr(function_app, "archive_report", lambda run_id, report: calls.append("archive") or "report-path")
    monkeypatch.setattr(function_app, "send_report", lambda report, run_id: calls.append("send") or {"status": "accepted"})
    function_app.waste_hunter(None)
    assert calls == ["archive", "send"]


def test_archive_failure_blocks_notification(monkeypatch):
    calls = []
    _install_common(monkeypatch)
    monkeypatch.setattr(function_app, "archive_report", lambda *args: (_ for _ in ()).throw(OSError("storage down")))
    monkeypatch.setattr(function_app, "send_report", lambda *args: calls.append("send"))
    result = function_app.waste_hunter(None)
    assert result["status"] == "partial"
    assert result["delivery"]["status"] == "not_archived"
    assert calls == []


def test_ambiguous_notification_is_unknown_and_not_retried(monkeypatch):
    calls = []
    _install_common(monkeypatch)
    def ambiguous(report, run_id):
        calls.append(run_id)
        raise function_app.DeliveryError("timeout", outcome="unknown")
    monkeypatch.setattr(function_app, "send_report", ambiguous)
    result = function_app.waste_hunter(None)
    assert result["delivery"]["status"] == "unknown"
    assert len(calls) == 1


def test_candidate_price_and_tags_are_included_in_manifest_and_report(monkeypatch):
    resource = {"type": "disk", "id": "disk-id", "name": "disk-1", "sku": "P10",
                "size_gb": 128, "location": "west", "tags": {}}
    _install_common(monkeypatch, {"disk": lambda: [resource]})
    monkeypatch.setattr(function_app, "estimate_cost", lambda r: SimpleNamespace(to_dict=lambda: {
        "status": "priced", "amount": 5.0, "currency": "USD", "reason": None, "source": "user_override", "unit": "USD/month"
    }))
    saved = {}
    monkeypatch.setattr(function_app, "archive_report", lambda run_id, report: saved.update(report=report) or "path")
    result = function_app.waste_hunter(None)
    assert result["priced_exposure_monthly"]["amount"] == 5
    assert "candidate" in saved["report"]
    assert "estimated monthly cost exposure" in saved["report"].lower()


def test_manifest_snapshots_are_append_only(monkeypatch):
    snapshots = []
    _install_common(monkeypatch)
    monkeypatch.setattr(function_app, "archive_manifest", lambda manifest: snapshots.append(deepcopy(manifest)))
    function_app.waste_hunter(None)
    revisions = [snapshot["manifest_revision"] for snapshot in snapshots]
    assert revisions == sorted(set(revisions))


def test_duplicate_scheduled_trigger_returns_previous_without_resending(monkeypatch):
    previous = {"run_id": "same-run", "manifest_revision": 2, "status": "complete",
                "delivery": {"status": "accepted", "report_path": "runs/same-run/report.md"}, "errors": []}
    _install_common(monkeypatch)
    monkeypatch.setattr(function_app, "load_latest_manifest", lambda run_id: previous)
    calls = []
    monkeypatch.setattr(function_app, "send_report", lambda *args: calls.append("send"))
    timer = SimpleNamespace(schedule_status={"last": "2026-10-26T14:00:00+00:00"})
    result = function_app.waste_hunter(timer)
    assert result["duplicate_trigger"] is True
    assert calls == []


def test_replayed_pending_notification_becomes_unknown_and_is_not_retried(monkeypatch):
    previous = {"run_id": "same-run", "manifest_revision": 2, "status": "report_ready",
                "delivery": {"status": "pending", "report_path": "runs/same-run/report.md"}, "errors": []}
    saved = []
    _install_common(monkeypatch)
    monkeypatch.setattr(function_app, "load_latest_manifest", lambda run_id: previous)
    monkeypatch.setattr(function_app, "archive_manifest", lambda manifest: saved.append(deepcopy(manifest)))
    calls = []
    monkeypatch.setattr(function_app, "send_report", lambda *args: calls.append("send"))
    result = function_app.waste_hunter(SimpleNamespace(schedule_status={"last": "tick"}))
    assert result["delivery"]["status"] == "unknown"
    assert result["duplicate_trigger"] is True
    assert calls == []
    assert saved[-1]["delivery"]["status"] == "unknown"


def test_run_configuration_validation_fails_closed(monkeypatch):
    _install_common(monkeypatch)
    monkeypatch.setenv("MAX_RESOURCES_PER_RUN", "0")
    result = function_app.waste_hunter(None)
    assert result["status"] == "failed"
    assert result["errors"][0]["stage"] == "configuration"
