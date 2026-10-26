import pytest

from delivery import blob, lgapp_sender


def test_send_report_requires_env(monkeypatch):
    monkeypatch.delenv("LOGIC_APP_WEBHOOK", raising=False)
    with pytest.raises(ValueError):
        lgapp_sender.send_report("hi", "run-1")


def test_sender_includes_stable_idempotency_key(monkeypatch):
    monkeypatch.setenv("LOGIC_APP_WEBHOOK", "https://example.invalid/hook")
    captured = {}
    class Response:
        status_code = 202
    def post(url, **kwargs):
        captured.update(kwargs)
        return Response()
    monkeypatch.setattr(lgapp_sender.requests, "post", post)
    assert lgapp_sender.send_report("report", "run-1")["status"] == "accepted"
    assert captured["headers"]["Idempotency-Key"] == "run-1"


def test_sender_classifies_network_timeout_as_unknown(monkeypatch):
    monkeypatch.setenv("LOGIC_APP_WEBHOOK", "https://example.invalid/hook")
    monkeypatch.setattr(lgapp_sender.requests, "post", lambda *a, **k: (_ for _ in ()).throw(lgapp_sender.requests.Timeout()))
    with pytest.raises(lgapp_sender.DeliveryError) as exc:
        lgapp_sender.send_report("report", "run-1")
    assert exc.value.outcome == "unknown"


def test_sender_classifies_http_client_rejection(monkeypatch):
    monkeypatch.setenv("LOGIC_APP_WEBHOOK", "https://example.invalid/hook")
    class Response:
        status_code = 400
    monkeypatch.setattr(lgapp_sender.requests, "post", lambda *a, **k: Response())
    with pytest.raises(lgapp_sender.DeliveryError) as exc:
        lgapp_sender.send_report("report", "run-1")
    assert exc.value.outcome == "rejected"


def test_blob_uses_managed_identity_when_account_url_is_configured(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://storage.blob.core.windows.net")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    captured = {}
    class Service:
        def get_container_client(self, container):
            captured["container"] = container
            return self
        def upload_blob(self, name, data, **kwargs):
            captured.update(name=name, data=data, **kwargs)
    class Credential:
        def __init__(self):
            captured["credential"] = True
    monkeypatch.setattr(blob, "DefaultAzureCredential", Credential)
    monkeypatch.setattr(blob, "BlobServiceClient", lambda url, credential: captured.update(url=url) or Service())
    assert blob.archive_report("run-1", "report") == "runs/run-1/report.md"
    assert captured["credential"] is True
    assert captured["overwrite"] is False


def test_manifest_blob_names_are_versioned(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://storage.blob.core.windows.net")
    class Service:
        def get_container_client(self, container):
            return self
        def upload_blob(self, name, data, **kwargs):
            self.name = name
    service = Service()
    monkeypatch.setattr(blob, "DefaultAzureCredential", lambda: object())
    monkeypatch.setattr(blob, "BlobServiceClient", lambda *a, **k: service)
    path = blob.archive_manifest({"run_id": "run-1", "manifest_revision": 7})
    assert path == "runs/run-1/manifests/0007.json"
