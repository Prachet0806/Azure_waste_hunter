import os

import requests


class DeliveryError(RuntimeError):
    def __init__(self, message, *, outcome):
        super().__init__(message)
        self.outcome = outcome


def send_report(report: str, run_id: str):
    webhook = os.environ.get("LOGIC_APP_WEBHOOK")
    if not webhook:
        raise ValueError("LOGIC_APP_WEBHOOK is not set")

    payload = {
        "subject": "Azure Waste Hunter — Weekly Cost Optimization Report",
        "body": report
    }

    try:
        response = requests.post(webhook, json=payload, timeout=10,
                                 headers={"Idempotency-Key": run_id, "X-Waste-Hunter-Run-Id": run_id})
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise DeliveryError("Webhook outcome is unknown after a network interruption.", outcome="unknown") from exc
    if response.status_code >= 500:
        raise DeliveryError(f"Webhook returned HTTP {response.status_code}; delivery outcome is unknown.", outcome="unknown")
    if response.status_code >= 400:
        raise DeliveryError(f"Webhook rejected the report with HTTP {response.status_code}.", outcome="rejected")
    return {"status": "accepted", "http_status": response.status_code}
