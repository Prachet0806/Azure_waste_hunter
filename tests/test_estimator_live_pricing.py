from cost_engine import estimator


def test_live_price_pagination_reads_all_pages(monkeypatch):
    estimator._price_cache.clear()
    estimator._price_cache_ts.clear()
    calls = []
    class Response:
        def __init__(self, items, next_page=None):
            self.items = items
            self.next_page = next_page
        def raise_for_status(self):
            return None
        def json(self):
            return {"Items": self.items, "NextPageLink": self.next_page}
    def get(url, params=None, timeout=10):
        calls.append((url, params))
        if len(calls) == 1:
            return Response([], "https://prices.example/page-2")
        return Response([{"unitPrice": 2}])
    monkeypatch.setattr(estimator.requests, "get", get)
    assert estimator._price_rows("filter") == [{"unitPrice": 2}]
    assert calls == [(estimator.AZURE_PRICING_ENDPOINT, {"$filter": "filter"}),
                     ("https://prices.example/page-2", None)]
