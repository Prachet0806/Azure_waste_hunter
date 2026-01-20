from azure.mgmt.monitor import MonitorManagementClient
from shared.auth import get_credential, get_subscription_id
from shared.retry import with_retries
import os, datetime

def enrich_db(db):
    cred = get_credential()
    sub = get_subscription_id()
    monitor = MonitorManagementClient(cred, sub)

    end = datetime.datetime.utcnow()
    start = end - datetime.timedelta(days=7)

    metrics = with_retries(lambda: monitor.metrics.list(
        db["id"],
        timespan=f"{start.isoformat()}/{end.isoformat()}",
        interval="P1D",
        metricnames="cpu_percent",
        aggregation="Average",
    ))

    avgs = [pt.average for m in metrics.value for ts in m.timeseries for pt in ts.data if pt.average]
    avg = sum(avgs)/len(avgs) if avgs else None

    db["avg_cpu"] = round(avg, 2) if avg is not None else None
    db["idle"] = avg is None or avg < 5

    return db
