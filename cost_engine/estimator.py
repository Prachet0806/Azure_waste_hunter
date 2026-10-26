"""Conservative monthly price estimates with explicit provenance."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from shared.retry import with_retries

HOURS_PER_MONTH = 730
AZURE_PRICING_ENDPOINT = "https://prices.azure.com/api/retail/prices"
_price_cache: dict[str, Any] = {}
_price_cache_ts: dict[str, float] = {}


@dataclass(frozen=True)
class PricingResult:
    amount: float | None
    currency: str | None
    unit: str
    period: str
    source: str
    sku: str | None
    meter: str | None
    retrieved_at: str
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(resource: dict, *, amount=None, unit="USD/month", source="none", meter=None,
            status="unknown", reason=None, currency="USD") -> PricingResult:
    if amount is not None and not math.isfinite(float(amount)):
        amount = None
        status = "unknown"
        reason = reason or "Price amount is not finite."
    return PricingResult(
        amount=round(float(amount), 4) if amount is not None else None,
        currency=currency if amount is not None else None,
        unit=unit,
        period="month",
        source=source,
        sku=resource.get("vm_size") if resource.get("type") == "vm" else resource.get("sku"),
        meter=meter,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        reason=reason,
    )


def _cache_ttl() -> int:
    return int(os.getenv("PRICING_CACHE_TTL_SECONDS", "3600"))


def _load_overrides() -> dict[str, Any]:
    raw = os.getenv("PRICING_JSON")
    if not raw and os.getenv("PRICING_FILE"):
        with open(os.environ["PRICING_FILE"], encoding="utf-8") as pricing_file:
            raw = pricing_file.read()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("PRICING_JSON/PRICING_FILE must be a JSON object")
    validated: dict[str, Any] = {}
    for category, mapping in data.items():
        category = category.lower()
        if category not in {"vm", "disk", "lb", "postgres"} or not isinstance(mapping, dict):
            raise ValueError("Pricing overrides must map vm/disk/lb/postgres to SKU-price objects")
        clean = {}
        for sku, amount in mapping.items():
            if not isinstance(sku, str) or not sku.strip():
                raise ValueError("Pricing override SKU keys must be nonempty strings")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                raise ValueError(f"Pricing override for {sku!r} must be numeric")
            if not math.isfinite(amount) or amount <= 0:
                raise ValueError(f"Pricing override for {sku!r} must be finite and greater than zero")
            clean[sku.casefold()] = float(amount)
        validated[category] = clean
    return validated


def _price_rows(filter_str: str) -> list[dict[str, Any]]:
    ttl = _cache_ttl()
    now = time.time()
    cached = _price_cache.get(filter_str)
    if filter_str in _price_cache and now - _price_cache_ts.get(filter_str, 0) < ttl:
        return cached
    url: str | None = AZURE_PRICING_ENDPOINT
    params: dict[str, str] | None = {"$filter": filter_str}
    rows: list[dict[str, Any]] = []
    while url:
        def fetch_page():
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        payload = with_retries(fetch_page)
        if not isinstance(payload, dict):
            raise ValueError("Retail pricing response must be an object")
        rows.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
        params = None
    _price_cache[filter_str] = rows
    _price_cache_ts[filter_str] = now
    return rows


def _live_monthly_price(resource: dict) -> PricingResult:
    resource_type = resource.get("type")
    sku = resource.get("vm_size") if resource_type == "vm" else resource.get("sku")
    location = resource.get("location")
    if not sku or not location:
        return _result(resource, reason="SKU or region is missing.")
    if resource_type not in {"vm", "disk"}:
        return _result(resource, reason="A defensible single-meter monthly price is unavailable for this resource shape.")
    service = "Virtual Machines" if resource_type == "vm" else "Storage"
    clauses = [
        f"serviceName eq '{service}'",
        f"armSkuName eq '{sku}'",
        f"armRegionName eq '{location.lower()}'",
        "priceType eq 'Consumption'",
    ]
    if resource_type == "disk":
        clauses.append("productName contains 'Managed Disks'")
    query = " and ".join(clauses)
    try:
        rows = _price_rows(query)
    except Exception as exc:
        return _result(resource, reason=f"Retail pricing lookup failed: {type(exc).__name__}.")
    exact = [row for row in rows if isinstance(row, dict) and
             str(row.get("armSkuName") or "").casefold() == sku.casefold()
             and str(row.get("armRegionName") or "").casefold() == location.casefold()
             and row.get("serviceName") == service
             and row.get("priceType") == "Consumption"]
    priced = [row for row in exact if isinstance(row.get("unitPrice"), (int, float))
              and math.isfinite(row["unitPrice"]) and row["unitPrice"] > 0
              and row.get("currencyCode") == "USD"]
    if len(priced) != 1:
        reason = "No exact USD meter matched." if not priced else "Multiple meters matched; monthly cost is ambiguous."
        return _result(resource, reason=reason)
    row = priced[0]
    unit = str(row.get("unitOfMeasure", ""))
    amount = float(row["unitPrice"])
    if resource_type == "vm" and unit.casefold() in {"1 hour", "hour"}:
        amount *= HOURS_PER_MONTH
        normalized_unit = "USD/month (hourly retail rate × 730)"
    elif resource_type == "disk" and unit.casefold() in {"1 gb/month", "gb/month", "1 gib/month", "gib/month"}:
        size = resource.get("size_gb")
        if isinstance(size, bool) or not isinstance(size, (int, float)) or size <= 0:
            return _result(resource, reason="Disk size is missing or invalid.")
        amount *= size
        normalized_unit = "USD/month (per-GB monthly rate × disk size)"
    else:
        return _result(resource, reason=f"Unsupported pricing unit {unit!r}; no monthly normalization applied.")
    return _result(resource, amount=amount, unit=normalized_unit, source="azure_retail_api",
                   meter=row.get("meterName"), status="priced")


def estimate_cost(resource: dict) -> PricingResult:
    """Return a monthly exposure estimate or a structured unknown result.

    Explicit override values are monthly USD amounts; disk overrides are USD/GB/month.
    """
    resource_type = resource.get("type")
    if resource_type not in {"vm", "disk", "lb", "postgres"}:
        return _result(resource, reason="Unsupported resource type.")
    mode = os.getenv("PRICING_MODE", "live").lower()
    if mode == "live":
        live_result = _live_monthly_price(resource)
        if live_result.status == "priced":
            return live_result
    elif mode != "static":
        return _result(resource, reason=f"Unsupported PRICING_MODE {mode!r}.")

    overrides = _load_overrides()
    sku = resource.get("vm_size") if resource_type == "vm" else resource.get("sku")
    override = overrides.get(resource_type, {}).get(str(sku).casefold()) if sku else None
    if override is None:
        live_reason = live_result.reason if mode == "live" else "No explicit monthly price override is configured."
        return _result(resource, reason=live_reason or "Price is unknown.")
    amount = override
    unit = "USD/month (explicit override)"
    if resource_type == "disk":
        size = resource.get("size_gb")
        if isinstance(size, bool) or not isinstance(size, (int, float)) or size <= 0:
            return _result(resource, reason="Disk size is missing or invalid.")
        amount *= size
        unit = "USD/month (override rate per GB/month × disk size)"
    return _result(resource, amount=amount, unit=unit, source="user_override", status="priced",
                   reason="Explicit price override; not a measured bill amount.")
