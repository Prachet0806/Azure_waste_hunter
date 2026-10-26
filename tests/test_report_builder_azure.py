from reporting.report_builder import build_report


def test_report_exposes_run_coverage_and_unknown_financials():
    manifest = {
        "run_id": "run-1", "status": "partial", "inventory_complete": False,
        "priced_exposure_monthly": {"amount": 12.5, "priced_count": 1, "unpriced_count": 1},
        "inventory": {"vm": {"queries_attempted": 1, "queries_succeeded": 0, "resources_discovered": 0}},
        "errors": [{"stage": "discovery_vm", "category": "authorization", "message": "denied"}],
        "delivery": {"status": "unknown"},
    }
    resources = [{"type": "vm", "name": "web", "location": "west", "assessment_status": "unassessed",
                  "assessment_reason": "Insufficient metrics", "metric_coverage": {"sample_count": 1,
                  "expected_samples": 7, "coverage": 1 / 7}, "price": {"status": "unknown", "reason": "No meter"},
                  "tag_assessment": {"status": "compliant", "violations": []}}]
    report = build_report(resources, manifest)
    assert "Run ID: `run-1`" in report
    assert "Inventory complete: **False**" in report
    assert "unpriced candidates: 1" in report
    assert "unknown** — No meter" in report
    assert "authorization" in report
    assert "not verified avoidable spend" in report
