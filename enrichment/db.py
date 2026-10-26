from datetime import datetime, timedelta, timezone

from azure.mgmt.monitor import MonitorManagementClient

from shared.auth import get_credential, get_subscription_id
from shared.metrics import coverage_status, metric_values
from shared.retry import with_retries


def enrich_db(db):
    cred = get_credential()
    sub = get_subscription_id(db)
    monitor = MonitorManagementClient(cred, sub)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    metrics = with_retries(lambda: monitor.metrics.list(
        db["id"],
        timespan=f"{start.isoformat()}/{end.isoformat()}",
        interval="P1D",
        metricnames="cpu_percent",
        aggregation="Average",
    ))

    avgs = metric_values(metrics)
    avg = sum(avgs)/len(avgs) if avgs else None

    db["avg_cpu"] = round(avg, 2) if avg is not None else None
    db["metric_coverage"] = coverage_status(avgs)
    if not db["metric_coverage"]["sufficient"]:
        db["assessment_status"] = "unassessed"
        db["assessment_reason"] = "Insufficient CPU metric coverage; missing data does not establish idleness."
    elif (db.get("state") or "").lower() == "stopped":
        db["assessment_status"] = "candidate"
        db["assessment_reason"] = "Server is stopped; stopped state alone does not establish avoidable spend."
    elif avg < 5:
        db["assessment_status"] = "candidate"
        db["assessment_reason"] = "Low CPU is a review signal, not proof that a database is waste."
    else:
        db["assessment_status"] = "active"
        db["assessment_reason"] = "Observed CPU is not below the review threshold."

    return db
