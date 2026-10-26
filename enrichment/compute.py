import os
from datetime import datetime, timedelta, timezone

from azure.mgmt.monitor import MonitorManagementClient

from shared.auth import get_credential, get_subscription_id
from shared.metrics import coverage_status, metric_values
from shared.retry import with_retries

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "2"))

def enrich_vm(vm):
    cred = get_credential()
    sub = get_subscription_id(vm)
    monitor = MonitorManagementClient(cred, sub)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    metrics = with_retries(lambda: monitor.metrics.list(
        vm["id"],
        timespan=f"{start.isoformat()}/{end.isoformat()}",
        interval="P1D",
        metricnames="Percentage CPU",
        aggregation="Average",
    ))

    avgs = metric_values(metrics)
    avg = sum(avgs)/len(avgs) if avgs else None

    vm["avg_cpu"] = round(avg, 2) if avg is not None else None
    vm["metric_coverage"] = coverage_status(avgs)
    if not vm["metric_coverage"]["sufficient"]:
        vm["assessment_status"] = "unassessed"
        vm["assessment_reason"] = "Insufficient CPU metric coverage for the seven-day window."
    elif avg < CPU_THRESHOLD:
        vm["assessment_status"] = "validated_idle"
        vm["assessment_reason"] = f"Seven-day average CPU {avg:.2f}% is below {CPU_THRESHOLD:.2f}%."
    else:
        vm["assessment_status"] = "active"
        vm["assessment_reason"] = f"Seven-day average CPU {avg:.2f}% is not below the idle threshold."

    return vm
