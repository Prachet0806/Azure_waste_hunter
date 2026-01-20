import os, datetime
from azure.identity import DefaultAzureCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from shared.retry import with_retries

cred = DefaultAzureCredential()
client = ResourceGraphClient(cred)

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "2"))


def _get_subscriptions():
    subs = os.getenv("AZURE_SUBSCRIPTIONS", "")
    if not subs:
        raise ValueError("AZURE_SUBSCRIPTIONS is not set")
    return [s.strip() for s in subs.split(",") if s.strip()]

def query(kql):
    req = QueryRequest(subscriptions=_get_subscriptions(), query=kql)
    return with_retries(lambda: client.resources(req).data)

def _normalize(resources, type_name):
    normalized = []
    for r in resources:
        item = dict(r)
        item["type"] = type_name
        item["tags"] = item.get("tags") or {}
        if type_name == "vm" and "vmSize" in item and "vm_size" not in item:
            item["vm_size"] = item.pop("vmSize")
        normalized.append(item)
    return normalized

# ---------------- Idle VM Candidates ----------------
def scan_idle_vms():
    kql = """
    Resources
    | where type == 'microsoft.compute/virtualmachines'
    | project id, name, location, tags, vmSize=properties.hardwareProfile.vmSize
    """
    return _normalize(query(kql), "vm")

# ---------------- Unattached Disks ----------------
def scan_unattached_disks():
    kql = """
    Resources
    | where type == 'microsoft.compute/disks'
    | where isnull(properties.managedBy)
    | project id, name, location, tags, size_gb=properties.diskSizeGB, sku=sku.name
    """
    return _normalize(query(kql), "disk")

# ---------------- Unused Load Balancers ----------------
def scan_unused_load_balancers():
    kql = """
    Resources
    | where type == 'microsoft.network/loadbalancers'
    | where array_length(properties.backendAddressPools) == 0
    | project id, name, location, tags
    """
    return _normalize(query(kql), "lb")

# ---------------- Stopped PostgreSQL Servers ----------------
def scan_idle_databases():
    kql = """
    Resources
    | where type == 'microsoft.dbforpostgresql/flexibleservers'
    | where properties.state == 'Stopped'
    | project id, name, location, tags
    """
    return _normalize(query(kql), "postgres")
