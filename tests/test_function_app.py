import function_app


def test_waste_hunter_partial_on_scan_error(monkeypatch):
    def good_scan():
        return [{"type": "vm", "id": "vm-1", "vm_size": "Standard_B2s", "location": "westeurope", "tags": {}}]

    def bad_scan():
        raise RuntimeError("boom")

    monkeypatch.setattr(function_app, "scan_idle_vms", bad_scan)
    monkeypatch.setattr(function_app, "scan_unattached_disks", good_scan)
    monkeypatch.setattr(function_app, "scan_unused_load_balancers", good_scan)
    monkeypatch.setattr(function_app, "scan_idle_databases", good_scan)

    monkeypatch.setattr(function_app, "enrich_vm", lambda r: {**r, "idle": True})
    monkeypatch.setattr(function_app, "enrich_disk", lambda r: {**r, "idle": True})
    monkeypatch.setattr(function_app, "enrich_lb", lambda r: {**r, "idle": True})
    monkeypatch.setattr(function_app, "enrich_db", lambda r: {**r, "idle": True})

    monkeypatch.setattr(function_app, "estimate_cost", lambda r: 1.0)
    monkeypatch.setattr(function_app, "check_tags", lambda r: [])

    monkeypatch.setattr(function_app, "send_report", lambda report: None)
    monkeypatch.setattr(function_app, "archive_report", lambda report: None)

    result = function_app.waste_hunter(None)

    assert result["status"] == "partial"
    assert len(result["scan_errors"]) == 1


def test_waste_hunter_partial_on_delivery_error(monkeypatch):
    def good_scan():
        return [{"type": "vm", "id": "vm-1", "vm_size": "Standard_B2s", "location": "westeurope", "tags": {}}]

    def bad_delivery(report):
        raise RuntimeError("boom")

    monkeypatch.setattr(function_app, "scan_idle_vms", good_scan)
    monkeypatch.setattr(function_app, "scan_unattached_disks", lambda: [])
    monkeypatch.setattr(function_app, "scan_unused_load_balancers", lambda: [])
    monkeypatch.setattr(function_app, "scan_idle_databases", lambda: [])

    monkeypatch.setattr(function_app, "enrich_vm", lambda r: {**r, "idle": True})
    monkeypatch.setattr(function_app, "estimate_cost", lambda r: 1.0)
    monkeypatch.setattr(function_app, "check_tags", lambda r: [])

    monkeypatch.setattr(function_app, "send_report", bad_delivery)
    monkeypatch.setattr(function_app, "archive_report", lambda report: None)

    result = function_app.waste_hunter(None)

    assert result["status"] == "partial"
    assert len(result["delivery_errors"]) == 1
