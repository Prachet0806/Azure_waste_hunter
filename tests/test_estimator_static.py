import json

import pytest

from cost_engine import estimator


@pytest.fixture(autouse=True)
def reset_price_cache():
    estimator._price_cache.clear()
    estimator._price_cache_ts.clear()


def test_missing_sku_price_is_unknown_not_a_default(monkeypatch):
    monkeypatch.setenv("PRICING_MODE", "static")
    monkeypatch.delenv("PRICING_JSON", raising=False)
    result = estimator.estimate_cost({"type": "vm", "vm_size": "Unlisted"})
    assert result.status == "unknown"
    assert result.amount is None


def test_explicit_vm_override_is_monthly_usd(monkeypatch):
    monkeypatch.setenv("PRICING_MODE", "static")
    monkeypatch.setenv("PRICING_JSON", json.dumps({"VM": {"Standard_B2s": 36}}))
    result = estimator.estimate_cost({"type": "vm", "vm_size": "Standard_B2s"})
    assert result.amount == 36
    assert result.currency == "USD"
    assert result.period == "month"
    assert result.source == "user_override"


def test_disk_override_requires_positive_size_and_multiplies_per_gb(monkeypatch):
    monkeypatch.setenv("PRICING_MODE", "static")
    monkeypatch.setenv("PRICING_JSON", json.dumps({"disk": {"Premium_LRS": 0.12}}))
    result = estimator.estimate_cost({"type": "disk", "sku": "Premium_LRS", "size_gb": 100})
    assert result.amount == 12
    missing_size = estimator.estimate_cost({"type": "disk", "sku": "Premium_LRS"})
    assert missing_size.status == "unknown"


@pytest.mark.parametrize("value", [0, -1, True, "bad"])
def test_invalid_override_fails_configuration(monkeypatch, value):
    monkeypatch.setenv("PRICING_MODE", "static")
    monkeypatch.setenv("PRICING_JSON", json.dumps({"vm": {"sku": value}}))
    with pytest.raises(ValueError):
        estimator.estimate_cost({"type": "vm", "vm_size": "sku"})


def test_live_price_uses_only_a_unique_exact_hour_meter(monkeypatch):
    monkeypatch.setenv("PRICING_MODE", "live")
    monkeypatch.delenv("PRICING_JSON", raising=False)
    monkeypatch.delenv("PRICING_FILE", raising=False)
    row = {"armSkuName": "Standard_B2s", "armRegionName": "westeurope",
           "serviceName": "Virtual Machines", "priceType": "Consumption",
           "unitPrice": 0.05, "unitOfMeasure": "1 Hour", "currencyCode": "USD", "meterName": "Compute"}
    monkeypatch.setattr(estimator, "_price_rows", lambda _: [row])
    result = estimator.estimate_cost({"type": "vm", "vm_size": "Standard_B2s", "location": "westeurope"})
    assert result.amount == 36.5
    assert result.meter == "Compute"
    assert result.unit.startswith("USD/month")


def test_ambiguous_live_meter_remains_unknown(monkeypatch):
    monkeypatch.setenv("PRICING_MODE", "live")
    monkeypatch.delenv("PRICING_JSON", raising=False)
    monkeypatch.delenv("PRICING_FILE", raising=False)
    row = {"armSkuName": "B2", "armRegionName": "west", "serviceName": "Virtual Machines",
           "priceType": "Consumption", "unitPrice": 1, "unitOfMeasure": "1 Hour", "currencyCode": "USD"}
    monkeypatch.setattr(estimator, "_price_rows", lambda _: [row, dict(row)])
    result = estimator.estimate_cost({"type": "vm", "vm_size": "B2", "location": "west"})
    assert result.status == "unknown"
    assert result.amount is None


def test_live_pricing_does_not_fallback_after_lookup_failure(monkeypatch):
    monkeypatch.setenv("PRICING_MODE", "live")
    monkeypatch.setenv("PRICING_JSON", json.dumps({"vm": {"B2": 99}}))
    monkeypatch.setattr(estimator, "_price_rows", lambda _: (_ for _ in ()).throw(RuntimeError("network")))
    result = estimator.estimate_cost({"type": "vm", "vm_size": "B2", "location": "west"})
    assert result.status == "priced"
    assert result.amount == 99
    assert result.source == "user_override"
