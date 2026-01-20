import os
import requests

def send_report(report: str):
    webhook = os.environ.get("LOGIC_APP_WEBHOOK")
    if not webhook:
        raise ValueError("LOGIC_APP_WEBHOOK is not set")

    payload = {
        "subject": "Azure Waste Hunter — Weekly Cost Optimization Report",
        "body": report
    }

    r = requests.post(webhook, json=payload, timeout=10)
    r.raise_for_status()
