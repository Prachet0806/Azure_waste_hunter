import os
import json
import time
import requests

HOURS_PER_MONTH = 730

DEFAULT_PRICING = {
    "vm": {"Standard_B2s": 36.0, "Standard_D2s_v5": 70.0},
    "disk": {"Premium_LRS": 0.12, "Standard_LRS": 0.05},
    "lb": 18.0,
    "postgres": 120.0
}

AZURE_PRICING_ENDPOINT = "https://prices.azure.com/api/retail/prices"

_price_cache = {}
_price_cache_ts = {}


def _cache_ttl():
    return int(os.getenv("PRICING_CACHE_TTL_SECONDS", "3600"))


def _normalize_pricing_keys(pricing: dict) -> dict:
    normalized = {}
    for k, v in pricing.items():
        normalized[k.lower()] = v
    return normalized


def _merge_pricing(base: dict, overrides: dict) -> dict:
    merged = {
        "vm": dict(base.get("vm", {})),
        "disk": dict(base.get("disk", {})),
        "lb": base.get("lb", 0.0),
        "postgres": base.get("postgres", 0.0),
    }
    for k, v in overrides.items():
        if k in ("vm", "disk") and isinstance(v, dict):
            merged[k].update(v)
        elif k in ("lb", "postgres"):
            merged[k] = v
    return merged


def _load_overrides() -> dict:
    raw = os.getenv("PRICING_JSON")
    if not raw:
        path = os.getenv("PRICING_FILE")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("PRICING_JSON/PRICING_FILE must be a JSON object")
    return _normalize_pricing_keys(data)


def _get_pricing() -> dict:
    overrides = _load_overrides()
    return _merge_pricing(DEFAULT_PRICING, overrides)


def _get_cached_price(key: str):
    ts = _price_cache_ts.get(key)
    if ts and (time.time() - ts) < _cache_ttl():
        return _price_cache.get(key)
    return None


def _set_cached_price(key: str, value):
    _price_cache[key] = value
    _price_cache_ts[key] = time.time()


def _fetch_price(filter_str: str):
    cached = _get_cached_price(filter_str)
    if cached is not None:
        return cached

    url = AZURE_PRICING_ENDPOINT
    params = {"$filter": filter_str}
    while url:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("Items", [])
        if items:
            price = items[0].get("unitPrice")
            _set_cached_price(filter_str, price)
            return price
        url = data.get("NextPageLink")
        params = None
    _set_cached_price(filter_str, None)
    return None


def _norm_location(resource: dict) -> str | None:
    loc = resource.get("location")
    return loc.lower() if isinstance(loc, str) and loc else None


def _live_vm_price(resource: dict):
    vm_size = resource.get("vm_size")
    location = _norm_location(resource)
    if not vm_size or not location:
        return None
    filter_str = (
        "serviceName eq 'Virtual Machines' and "
        f"armSkuName eq '{vm_size}' and "
        "priceType eq 'Consumption' and "
        f"armRegionName eq '{location}'"
    )
    return _fetch_price(filter_str)


def _live_disk_price(resource: dict):
    sku = resource.get("sku")
    size_gb = resource.get("size_gb")
    location = _norm_location(resource)
    if not sku or not size_gb or not location:
        return None
    filter_str = (
        "serviceName eq 'Storage' and "
        f"armSkuName eq '{sku}' and "
        "productName contains 'Managed Disks' and "
        f"armRegionName eq '{location}'"
    )
    unit_price = _fetch_price(filter_str)
    return unit_price * size_gb if unit_price is not None else None


def _live_lb_price(resource: dict):
    location = _norm_location(resource)
    if not location:
        return None
    filter_str = (
        "serviceName eq 'Load Balancer' and "
        "priceType eq 'Consumption' and "
        f"armRegionName eq '{location}'"
    )
    return _fetch_price(filter_str)


def _live_postgres_price(resource: dict):
    location = _norm_location(resource)
    if not location:
        return None
    filter_str = (
        "serviceName eq 'Azure Database for PostgreSQL' and "
        "priceType eq 'Consumption' and "
        f"armRegionName eq '{location}'"
    )
    return _fetch_price(filter_str)

def estimate_cost(resource: dict) -> float:
    t = resource["type"]
    pricing = _get_pricing()
    mode = os.getenv("PRICING_MODE", "static").lower()

    if t == "vm":
        if mode == "live":
            live = _live_vm_price(resource)
            if live is not None:
                return live
        return pricing["vm"].get(resource["vm_size"], 50.0)

    if t == "disk":
        if mode == "live":
            live = _live_disk_price(resource)
            if live is not None:
                return live
        return pricing["disk"].get(resource["sku"], 0.05) * resource["size_gb"]

    if t == "lb":
        if mode == "live":
            live = _live_lb_price(resource)
            if live is not None:
                return live
        return pricing["lb"]

    if t == "postgres":
        if mode == "live":
            live = _live_postgres_price(resource)
            if live is not None:
                return live
        return pricing["postgres"]

    return 0.0
