from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

import azure.functions as func

from compliance.tag_checker import check_tags
from cost_engine.estimator import estimate_cost
from delivery.blob import archive_manifest, archive_report, load_latest_manifest
from delivery.lgapp_sender import DeliveryError, send_report
from enrichment.compute import enrich_vm
from enrichment.db import enrich_db
from enrichment.disks import enrich_disk
from enrichment.load_balancer import enrich_lb
from observability.telemetry import log_event
from reporting.report_builder import build_report
from scanner.resource_graph import (
    scan_databases,
    scan_load_balancers,
    scan_unattached_disks,
    scan_vms,
)
from shared.run_manifest import new_run_manifest, snapshot

app = func.FunctionApp()


class RunDeadlineExceeded(TimeoutError):
    pass


def _error_category(error: Exception) -> str:
    if isinstance(error, DeliveryError):
        return f"delivery_{error.outcome}"
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    if status in (401, 403):
        return "authorization"
    if status == 429:
        return "throttled"
    if isinstance(status, int) and status >= 500:
        return "transient_service"
    if isinstance(error, (TimeoutError, ConnectionError)):
        return "timeout"
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return "invalid_data_or_configuration"
    return "unknown"


def _record_error(manifest: dict, stage: str, error: Exception) -> dict:
    item = {"stage": stage, "category": _error_category(error),
            "message": f"{type(error).__name__}: {error}"}
    manifest["errors"].append(item)
    return item


def _checkpoint(manifest: dict) -> None:
    archive_manifest(snapshot(manifest))


def _scheduled_run_id(timer) -> str:
    status = getattr(timer, "schedule_status", None)
    if isinstance(status, dict):
        scheduled = status.get("last") or status.get("Last")
        if scheduled:
            return str(uuid5(NAMESPACE_URL, f"azure-waste-hunter:{scheduled}"))
    return str(uuid4())


def _check_deadline(started: float, budget: int) -> None:
    if time.monotonic() - started >= budget:
        raise RunDeadlineExceeded(f"Run budget of {budget} seconds exceeded")


def _enricher(resource: dict):
    return {
        "vm": enrich_vm,
        "disk": enrich_disk,
        "lb": enrich_lb,
        "postgres": enrich_db,
    }.get(resource.get("type"))


@app.timer_trigger(schedule="0 0 14 * * 1", arg_name="timer")
def waste_hunter(timer: func.TimerRequest):
    started = time.monotonic()
    run_id = _scheduled_run_id(timer)
    previous = load_latest_manifest(run_id)
    if previous and previous.get("delivery", {}).get("report_path"):
        if previous.get("delivery", {}).get("status") == "pending":
            previous["delivery"]["status"] = "unknown"
            previous["errors"].append({"stage": "notification", "category": "delivery_unknown",
                                       "message": "Prior invocation ended after report archival; notification was not replayed."})
            previous["status"] = "partial"
            previous["completed_at"] = datetime.now(timezone.utc).isoformat()
            _checkpoint(previous)
        previous["duplicate_trigger"] = True
        log_event("waste_hunter", "run_complete", run_id=run_id, status=previous.get("status"),
                  duplicate_trigger=True)
        return previous
    manifest = new_run_manifest(run_id, previous_revision=previous.get("manifest_revision", 0) if previous else 0)
    if previous:
        manifest["restart_count"] = previous.get("restart_count", 0) + 1
    log_event("waste_hunter", "run_start", run_id=manifest["run_id"])
    _checkpoint(manifest)

    try:
        budget_seconds = int(os.getenv("RUN_BUDGET_SECONDS", "240"))
        max_resources = int(os.getenv("MAX_RESOURCES_PER_RUN", "500"))
        if budget_seconds < 1 or max_resources < 1:
            raise ValueError("RUN_BUDGET_SECONDS and MAX_RESOURCES_PER_RUN must be positive integers")
    except (TypeError, ValueError) as exc:
        _record_error(manifest, "configuration", exc)
        manifest["status"] = "failed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["run_duration_seconds"] = round(time.monotonic() - started, 3)
        _checkpoint(manifest)
        log_event("waste_hunter", "run_complete", run_id=manifest["run_id"], status="failed",
                  duration_seconds=manifest["run_duration_seconds"])
        return manifest

    resources: list[dict] = []
    scanners = {
        "vm": scan_vms,
        "disk": scan_unattached_disks,
        "lb": scan_load_balancers,
        "postgres": scan_databases,
    }
    for kind, scan in scanners.items():
        _check_deadline(started, budget_seconds)
        stage_started = time.monotonic()
        counts = {"queries_attempted": 1, "queries_succeeded": 0, "resources_discovered": 0}
        manifest["inventory"][kind] = counts
        try:
            found = scan()
            counts["queries_succeeded"] = 1
            counts["resources_discovered"] = len(found)
            resources.extend(found)
            manifest["stages"][f"discovery_{kind}"] = {"status": "succeeded"}
        except Exception as exc:
            manifest["stages"][f"discovery_{kind}"] = {"status": "failed"}
            _record_error(manifest, f"discovery_{kind}", exc)
        manifest["stages"][f"discovery_{kind}"]["duration_seconds"] = round(time.monotonic() - stage_started, 3)
        _checkpoint(manifest)

    manifest["inventory_complete"] = all(
        entry["queries_attempted"] == entry["queries_succeeded"]
        for entry in manifest["inventory"].values()
    )
    if len(resources) > max_resources:
        manifest["inventory_complete"] = False
        manifest["errors"].append({"stage": "inventory_limit", "category": "configured_limit",
                                   "message": f"Discovered {len(resources)} resources; capped processing at {max_resources}."})
        resources = resources[:max_resources]
        manifest["inventory"]["processing_limit"] = {"discovered": sum(row["resources_discovered"] for row in manifest["inventory"].values()),
                                                     "processed": max_resources}

    assessed: list[dict] = []
    enrichment_started = time.monotonic()
    for index, original in enumerate(resources):
        _check_deadline(started, budget_seconds)
        resource = dict(original)
        enrich = _enricher(resource)
        if resource.get("discovery_issues"):
            resource["assessment_status"] = "unassessed"
            resource["assessment_reason"] = "; ".join(resource["discovery_issues"])
        elif enrich is None:
            resource["assessment_status"] = "unassessed"
            resource["assessment_reason"] = f"Unknown resource type: {resource.get('type')}"
            _record_error(manifest, "enrichment", ValueError(resource["assessment_reason"]))
        else:
            try:
                resource = enrich(resource)
            except Exception as exc:
                resource["assessment_status"] = "unassessed"
                resource["assessment_reason"] = "Enrichment failed; no waste classification was made."
                _record_error(manifest, f"enrichment_{resource.get('type')}", exc)
        resource.setdefault("assessment_status", "unassessed")
        resource.setdefault("assessment_reason", "No assessment rationale was returned.")
        assessed.append(resource)
        if (index + 1) % 50 == 0:
            manifest["stages"]["enrichment"] = {"status": "running", "processed": index + 1}
            _checkpoint(manifest)
    manifest["stages"]["enrichment"] = {"status": "succeeded",
                                          "duration_seconds": round(time.monotonic() - enrichment_started, 3)}

    counts: dict[str, int] = {}
    candidates = []
    assessment_started = time.monotonic()
    for resource in assessed:
        state = resource["assessment_status"]
        counts[state] = counts.get(state, 0) + 1
        resource["tag_assessment"] = check_tags(resource)
        if state in {"candidate", "validated_idle"}:
            candidates.append(resource)
            try:
                price = estimate_cost(resource).to_dict()
            except Exception as exc:
                price = {"status": "unknown", "amount": None, "currency": None,
                         "unit": "USD/month", "source": "none", "reason": f"Pricing failed: {type(exc).__name__}.",
                         "sku": resource.get("sku") or resource.get("vm_size"), "meter": None}
                _record_error(manifest, "pricing", exc)
            resource["price"] = price
        else:
            resource["price"] = {"status": "not_applicable", "amount": None,
                                 "reason": "Resource was not a reviewed candidate."}
    manifest["assessment_counts"] = counts
    manifest["resources"] = [{
        "id": r.get("id"), "name": r.get("name"), "type": r.get("type"),
        "subscription_id": r.get("subscriptionId"), "assessment_status": r.get("assessment_status"),
        "assessment_reason": r.get("assessment_reason"), "metric_coverage": r.get("metric_coverage"),
        "price": r.get("price"), "tag_assessment": r.get("tag_assessment"),
    } for r in assessed]
    priced = [r["price"] for r in candidates if r["price"].get("status") == "priced"]
    unpriced = [r for r in candidates if r["price"].get("status") != "priced"]
    manifest["priced_exposure_monthly"] = {
        "currency": "USD",
        "amount": round(sum(item["amount"] for item in priced), 2),
        "priced_count": len(priced),
        "unpriced_count": len(unpriced),
    }
    manifest["stages"]["assessment_and_pricing"] = {
        "status": "succeeded", "duration_seconds": round(time.monotonic() - assessment_started, 3)
    }
    _checkpoint(manifest)

    manifest["delivery"] = {"status": "pending", "report_path": None, "attempts": 0}
    manifest["status"] = "report_ready"
    report = build_report(assessed, manifest)
    try:
        report_path = archive_report(manifest["run_id"], report)
        manifest["delivery"]["report_path"] = report_path
        manifest["stages"]["report_archive"] = {"status": "succeeded"}
    except Exception as exc:
        manifest["delivery"]["status"] = "not_archived"
        manifest["stages"]["report_archive"] = {"status": "failed"}
        _record_error(manifest, "report_archive", exc)
        manifest["status"] = "partial"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["run_duration_seconds"] = round(time.monotonic() - started, 3)
        _checkpoint(manifest)
        log_event("waste_hunter", "run_complete", run_id=manifest["run_id"], status=manifest["status"],
                  duration_seconds=manifest["run_duration_seconds"])
        return manifest

    # The report is immutable and archived before the one-time notification attempt.
    # The idempotency key is passed through; the receiver must honor it to deduplicate.
    _checkpoint(manifest)
    try:
        manifest["delivery"]["attempts"] = 1
        outcome = send_report(report, manifest["run_id"])
        manifest["delivery"].update(outcome)
        manifest["stages"]["notification"] = {"status": "succeeded"}
    except Exception as exc:
        delivery_status = exc.outcome if isinstance(exc, DeliveryError) else "unknown"
        manifest["delivery"]["status"] = delivery_status
        manifest["stages"]["notification"] = {"status": delivery_status}
        _record_error(manifest, "notification", exc)

    assessment_complete = counts.get("unassessed", 0) == 0
    tags_complete = all(r["tag_assessment"].get("status") != "unassessed" for r in assessed)
    pricing_complete = not unpriced
    stage_errors = bool(manifest["errors"])
    complete = (manifest["inventory_complete"] and assessment_complete and tags_complete and pricing_complete
                and manifest["delivery"].get("status") == "accepted" and not stage_errors)
    manifest["status"] = "complete" if complete else "partial"
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["run_duration_seconds"] = round(time.monotonic() - started, 3)
    try:
        _checkpoint(manifest)
        manifest["stages"]["final_manifest"] = {"status": "succeeded"}
    except Exception as exc:
        manifest["stages"]["final_manifest"] = {"status": "failed"}
        _record_error(manifest, "final_manifest", exc)
        manifest["status"] = "partial"
    log_event("waste_hunter", "run_complete", run_id=manifest["run_id"], status=manifest["status"],
              duration_seconds=manifest["run_duration_seconds"])
    return manifest
