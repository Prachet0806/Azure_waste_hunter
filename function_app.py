import azure.functions as func
from scanner.resource_graph import (
    scan_idle_vms,
    scan_unattached_disks,
    scan_unused_load_balancers,
    scan_idle_databases,
)

from enrichment.compute import enrich_vm
from enrichment.disks import enrich_disk
from enrichment.load_balancer import enrich_lb
from enrichment.db import enrich_db

from cost_engine.estimator import estimate_cost
from compliance.tag_checker import check_tags
from reporting.report_builder import build_report
from delivery.lgapp_sender import send_report
from delivery.blob import archive_report
from observability.telemetry import log_event

app = func.FunctionApp()

def _safe(stage, fn, *args):
    try:
        return fn(*args), None
    except Exception as e:
        return None, {"stage": stage, "error": str(e)}

@app.timer_trigger(schedule="0 0 14 * * 1", arg_name="timer")
def waste_hunter(timer: func.TimerRequest):
    log_event("waste_hunter", "run_start")
    resources = []
    scan_errors = []
    delivery_errors = []

    # Discovery (Resource Graph)
    for name, fn in [
        ("scan_idle_vms", scan_idle_vms),
        ("scan_unattached_disks", scan_unattached_disks),
        ("scan_unused_load_balancers", scan_unused_load_balancers),
        ("scan_idle_databases", scan_idle_databases),
    ]:
        data, err = _safe(name, fn)
        if err: scan_errors.append(err)
        else: resources += data
    log_event("waste_hunter", f"discovery_complete resources={len(resources)} errors={len(scan_errors)}")

    # Enrichment (Azure Monitor)
    enriched = []
    for r in resources:
        if r["type"] == "vm":
            r, err = _safe("enrich_vm", enrich_vm, r)
        elif r["type"] == "disk":
            r, err = _safe("enrich_disk", enrich_disk, r)
        elif r["type"] == "lb":
            r, err = _safe("enrich_lb", enrich_lb, r)
        elif r["type"] == "postgres":
            r, err = _safe("enrich_db", enrich_db, r)
        else:
            r, err = None, {"stage": "enrich", "error": f"unknown resource type: {r.get('type')}"}

        if err:
            scan_errors.append(err)
        elif r.get("idle") is True:
            enriched.append(r)
    log_event("waste_hunter", f"enrichment_complete idle={len(enriched)} errors={len(scan_errors)}")

    # Cost + Compliance
    for r in enriched:
        r["monthly_cost"] = estimate_cost(r)
        r["tag_violations"] = check_tags(r)

    report = build_report(enriched, scan_errors, [])

    # Delivery
    _, err = _safe("send_report", send_report, report)
    if err:
        delivery_errors.append(err)

    report = build_report(enriched, scan_errors, delivery_errors)

    _, err = _safe("archive_report", archive_report, report)
    if err:
        delivery_errors.append(err)
    log_event("waste_hunter", f"delivery_complete errors={len(delivery_errors)}")

    result = {
        "status": "ok" if not scan_errors and not delivery_errors else "partial",
        "resources": len(enriched),
        "monthly_waste": sum(r["monthly_cost"] for r in enriched),
        "scan_errors": scan_errors,
        "delivery_errors": delivery_errors,
    }
    log_event("waste_hunter", f"run_complete status={result['status']}")
    return result