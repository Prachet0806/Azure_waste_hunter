from azure.mgmt.monitor import MonitorManagementClient
from shared.auth import get_credential, get_subscription_id
from shared.retry import with_retries
import os, datetime

def enrich_lb(lb):
    cred = get_credential()
    sub = get_subscription_id()
    monitor = MonitorManagementClient(cred, sub)

    end = datetime.datetime.utcnow()
    start = end - datetime.timedelta(days=7)

    metrics = with_retries(lambda: monitor.metrics.list(
        lb["id"],
        timespan=f"{start.isoformat()}/{end.isoformat()}",
        interval="P1D",
        metricnames="VipAvailability",
        aggregation="Average",
    ))

    avgs = [pt.average for m in metrics.value for ts in m.timeseries for pt in ts.data if pt.average]
    lb["availability"] = round(sum(avgs)/len(avgs), 2) if avgs else None
    lb["idle"] = lb["availability"] is not None and lb["availability"] == 0
    return lb
