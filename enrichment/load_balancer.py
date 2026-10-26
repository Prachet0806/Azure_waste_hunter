from datetime import datetime, timedelta, timezone

from azure.mgmt.monitor import MonitorManagementClient

from shared.auth import get_credential, get_subscription_id
from shared.metrics import coverage_status, metric_values
from shared.retry import with_retries


def enrich_lb(lb):
    cred = get_credential()
    sub = get_subscription_id(lb)
    monitor = MonitorManagementClient(cred, sub)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    metrics = with_retries(lambda: monitor.metrics.list(
        lb["id"],
        timespan=f"{start.isoformat()}/{end.isoformat()}",
        interval="P1D",
        metricnames="VipAvailability",
        aggregation="Average",
    ))

    avgs = metric_values(metrics)
    lb["availability"] = round(sum(avgs)/len(avgs), 2) if avgs else None
    lb["metric_coverage"] = coverage_status(avgs)
    lb["assessment_status"] = "candidate" if not lb.get("backend_pool_count") else "active"
    lb["assessment_reason"] = (
        "No backend pools were discovered; review configuration and traffic before recommending action."
        if lb["assessment_status"] == "candidate"
        else "Backend pools exist; availability alone is not an idleness measure."
    )
    if not lb["metric_coverage"]["sufficient"]:
        lb["assessment_status"] = "unassessed"
        lb["assessment_reason"] = "Insufficient metric coverage; availability does not establish idleness."
    return lb
