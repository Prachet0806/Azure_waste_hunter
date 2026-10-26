from types import SimpleNamespace

from enrichment import compute, db, load_balancer
from shared.metrics import coverage_status, metric_values


def _response(values):
    points = [SimpleNamespace(average=value) for value in values]
    return SimpleNamespace(value=[SimpleNamespace(timeseries=[SimpleNamespace(data=points)])])


def test_metric_values_preserve_zero_and_ignore_missing_or_nonfinite():
    assert metric_values(_response([0, 1, None, float("nan")])) == [0.0, 1.0]
    assert coverage_status([0, 1])["sufficient"] is False


def test_vm_assessment_counts_zero_samples_and_requires_coverage(monkeypatch):
    monkeypatch.setattr(compute, "get_credential", lambda: object())
    monkeypatch.setattr(compute, "get_subscription_id", lambda resource: "sub-b")
    monkeypatch.setattr(compute, "MonitorManagementClient", lambda *a: SimpleNamespace(metrics=SimpleNamespace(list=lambda *a, **k: _response([0, 0, 0, 0, 0, 0, 0]))))
    result = compute.enrich_vm({"id": "vm", "subscriptionId": "sub-b"})
    assert result["avg_cpu"] == 0
    assert result["assessment_status"] == "validated_idle"
    assert result["metric_coverage"]["sample_count"] == 7


def test_vm_missing_metrics_are_unassessed(monkeypatch):
    monkeypatch.setattr(db, "get_credential", lambda: object())
    monkeypatch.setattr(db, "get_subscription_id", lambda resource: "sub")
    monkeypatch.setattr(db, "MonitorManagementClient", lambda *a: SimpleNamespace(metrics=SimpleNamespace(list=lambda *a, **k: _response([None, None]))))
    result = db.enrich_db({"id": "db", "state": "Stopped"})
    assert result["avg_cpu"] is None
    assert result["assessment_status"] == "unassessed"


def test_stopped_database_with_coverage_is_only_a_candidate(monkeypatch):
    monkeypatch.setattr(db, "get_credential", lambda: object())
    monkeypatch.setattr(db, "get_subscription_id", lambda resource: "sub")
    monkeypatch.setattr(db, "MonitorManagementClient", lambda *a: SimpleNamespace(metrics=SimpleNamespace(list=lambda *a, **k: _response([0, 0, 0, 0, 0, 0, 0]))))
    result = db.enrich_db({"id": "db", "state": "Stopped"})
    assert result["assessment_status"] == "candidate"
    assert "alone" in result["assessment_reason"]


def test_zero_availability_is_not_used_as_an_idle_predicate(monkeypatch):
    monkeypatch.setattr(load_balancer, "get_credential", lambda: object())
    monkeypatch.setattr(load_balancer, "get_subscription_id", lambda resource: "sub")
    monkeypatch.setattr(load_balancer, "MonitorManagementClient", lambda *a: SimpleNamespace(metrics=SimpleNamespace(list=lambda *a, **k: _response([0, 0, 0, 0, 0, 0, 0]))))
    result = load_balancer.enrich_lb({"id": "lb", "backend_pool_count": 1})
    assert result["availability"] == 0
    assert result["assessment_status"] == "active"
