import pytest

from delivery.blob import archive_report
from delivery.lgapp_sender import send_report


def test_send_report_requires_env(monkeypatch):
    monkeypatch.delenv("LOGIC_APP_WEBHOOK", raising=False)
    with pytest.raises(ValueError):
        send_report("hi")


def test_archive_report_requires_env(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    with pytest.raises(ValueError):
        archive_report("hi")
