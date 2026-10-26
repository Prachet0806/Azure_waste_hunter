import pytest

from shared.auth import get_subscription_id


def test_resource_subscription_takes_precedence(monkeypatch):
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "configured")
    assert get_subscription_id({"subscriptionId": "resource-sub"}) == "resource-sub"


def test_configured_subscription_fallbacks(monkeypatch):
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    monkeypatch.setenv("AZURE_SUBSCRIPTIONS", "first,second")
    assert get_subscription_id() == "first"
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "explicit")
    assert get_subscription_id() == "explicit"


def test_missing_subscription_configuration_is_an_error(monkeypatch):
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    monkeypatch.delenv("AZURE_SUBSCRIPTIONS", raising=False)
    with pytest.raises(ValueError):
        get_subscription_id()
