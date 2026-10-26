import os
import uuid

from azure.identity import DefaultAzureCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions

from shared.retry import with_retries

cred = DefaultAzureCredential()
client = ResourceGraphClient(cred)

def _get_subscriptions():
    subs = os.getenv("AZURE_SUBSCRIPTIONS", "")
    if not subs:
        raise ValueError("AZURE_SUBSCRIPTIONS is not set")
    result = []
    seen = set()
    for raw in subs.split(","):
        sub = raw.strip()
        if not sub:
            continue
        try:
            normalized = str(uuid.UUID(sub))
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid subscription ID: {sub!r}") from exc
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    if not result:
        raise ValueError("AZURE_SUBSCRIPTIONS contains no subscription IDs")
    return result

def query(kql):
    subscriptions = _get_subscriptions()
    result = []
    skip_token = None
    while True:
        options = QueryRequestOptions(skip_token=skip_token) if skip_token else None
        req = QueryRequest(subscriptions=subscriptions, query=kql, options=options)
        response = with_retries(lambda: client.resources(req))
        result.extend(response.data or [])
        skip_token = getattr(response, "skip_token", None)
        if not skip_token:
            return result

def _normalize(resources, type_name):
    normalized = []
    required_fields = {
        "vm": ("id", "name", "subscriptionId", "location", "vm_size"),
        "disk": ("id", "name", "subscriptionId", "location", "size_gb", "sku"),
        "lb": ("id", "name", "subscriptionId", "location", "backend_pool_count", "sku"),
        "postgres": ("id", "name", "subscriptionId", "location", "state", "sku"),
    }.get(type_name, ("id", "name"))
    for r in resources:
        item = dict(r)
        item["type"] = type_name
        if type_name == "vm" and "vmSize" in item and "vm_size" not in item:
            item["vm_size"] = item.pop("vmSize")
        if item.get("tags") is None:
            item["tags"] = {}
        issues = [f"missing required field: {field}" for field in required_fields if item.get(field) is None or item.get(field) == ""]
        if type_name == "disk" and isinstance(item.get("size_gb"), (int, float)) and item["size_gb"] <= 0:
            issues.append("disk size must be greater than zero")
        if issues:
            item["discovery_issues"] = issues
        normalized.append(item)
    return normalized

# ---------------- VM inventory ----------------
def scan_vms():
    kql = """
    Resources
    | where type == 'microsoft.compute/virtualmachines'
    | project id, name, subscriptionId, location, tags, vmSize=properties.hardwareProfile.vmSize
    """
    return _normalize(query(kql), "vm")

# ---------------- Unattached Disks ----------------
def scan_unattached_disks():
    kql = """
    Resources
    | where type == 'microsoft.compute/disks'
    | where isnull(properties.managedBy)
    | project id, name, subscriptionId, location, tags, size_gb=properties.diskSizeGB, sku=sku.name
    """
    return _normalize(query(kql), "disk")

# ---------------- Load-balancer candidates ----------------
def scan_load_balancers():
    kql = """
    Resources
    | where type == 'microsoft.network/loadbalancers'
    | where array_length(properties.backendAddressPools) == 0
    | project id, name, subscriptionId, location, tags, sku=sku.name, backend_pool_count=array_length(properties.backendAddressPools)
    """
    return _normalize(query(kql), "lb")

# ---------------- PostgreSQL inventory ----------------
def scan_databases():
    kql = """
    Resources
    | where type == 'microsoft.dbforpostgresql/flexibleservers'
    | project id, name, subscriptionId, location, tags, sku=sku.name, state=properties.state
    """
    return _normalize(query(kql), "postgres")
