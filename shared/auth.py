import os
from azure.identity import DefaultAzureCredential

_credential = None

def get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential

def get_subscription_id():
    sub = os.environ.get("AZURE_SUBSCRIPTION_ID")
    if not sub:
        subs = os.environ.get("AZURE_SUBSCRIPTIONS", "")
        sub = subs.split(",")[0].strip() if subs else None
    if not sub:
        raise ValueError("AZURE_SUBSCRIPTION_ID or AZURE_SUBSCRIPTIONS is not set")
    return sub