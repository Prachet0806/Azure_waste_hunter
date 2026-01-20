import json

from cost_engine import estimator


def test_pricing_json_override(monkeypatch):
    monkeypatch.setenv("PRICING_JSON", json.dumps({"vm": {"Standard_B2s": 99}}))
    monkeypatch.delenv("PRICING_MODE", raising=False)
    estimator._price_cache.clear()
    estimator._price_cache_ts.clear()

    resource = {"type": "vm", "vm_size": "Standard_B2s"}
    assert estimator.estimate_cost(resource) == 99


def test_pricing_file_override(monkeypatch, tmp_path):
    pricing = {"disk": {"Standard_LRS": 1.0}}
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(pricing), encoding="utf-8")
    monkeypatch.delenv("PRICING_JSON", raising=False)
    monkeypatch.setenv("PRICING_FILE", str(path))
    monkeypatch.delenv("PRICING_MODE", raising=False)
    estimator._price_cache.clear()
    estimator._price_cache_ts.clear()

    resource = {"type": "disk", "sku": "Standard_LRS", "size_gb": 2}
    assert estimator.estimate_cost(resource) == 2.0


def test_live_pricing_uses_retail_api(monkeypatch):
    class FakeResponse:
        def __init__(self, items):
            self._items = items

        def raise_for_status(self):
            return None

        def json(self):
            return {"Items": self._items, "NextPageLink": None}

    def fake_get(url, params=None, timeout=10):
        return FakeResponse([{"unitPrice": 12.34}])

    monkeypatch.setenv("PRICING_MODE", "live")
    monkeypatch.delenv("PRICING_JSON", raising=False)
    monkeypatch.delenv("PRICING_FILE", raising=False)
    monkeypatch.setattr(estimator.requests, "get", fake_get)
    estimator._price_cache.clear()
    estimator._price_cache_ts.clear()

    resource = {"type": "vm", "vm_size": "Standard_B2s", "location": "westeurope"}
    assert estimator.estimate_cost(resource) == 12.34
