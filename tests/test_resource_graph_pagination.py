from types import SimpleNamespace

import pytest

from scanner import resource_graph


def test_subscription_ids_are_validated_and_deduplicated(monkeypatch):
    monkeypatch.setenv("AZURE_SUBSCRIPTIONS", "00000000-0000-0000-0000-000000000001, 00000000-0000-0000-0000-000000000001")
    assert resource_graph._get_subscriptions() == ["00000000-0000-0000-0000-000000000001"]
    monkeypatch.setenv("AZURE_SUBSCRIPTIONS", "not-a-guid")
    with pytest.raises(ValueError, match="Invalid subscription ID"):
        resource_graph._get_subscriptions()


def test_query_follows_resource_graph_skip_tokens(monkeypatch):
    class Options:
        def __init__(self, skip_token=None):
            self.skip_token = skip_token

    class Request:
        def __init__(self, subscriptions, query, options=None):
            self.options = options

    calls = []

    class Client:
        def resources(self, request):
            calls.append(request.options.skip_token if request.options else None)
            if len(calls) == 1:
                return SimpleNamespace(data=[{"id": "one"}], skip_token="page-2")
            return SimpleNamespace(data=[{"id": "two"}], skip_token=None)

    monkeypatch.setenv("AZURE_SUBSCRIPTIONS", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setattr(resource_graph, "QueryRequest", Request)
    monkeypatch.setattr(resource_graph, "QueryRequestOptions", Options)
    monkeypatch.setattr(resource_graph, "client", Client())
    assert [r["id"] for r in resource_graph.query("Resources") ] == ["one", "two"]
    assert calls == [None, "page-2"]


def test_normalize_marks_missing_pricing_and_identity_fields():
    item = resource_graph._normalize([{"id": "disk-1", "type": "disk", "tags": {}}], "disk")[0]
    assert "discovery_issues" in item
    assert any("subscriptionId" in issue for issue in item["discovery_issues"])
