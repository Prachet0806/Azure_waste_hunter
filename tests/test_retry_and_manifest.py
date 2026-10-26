from types import SimpleNamespace

import pytest

from shared.retry import is_transient_error, with_retries
from shared.run_manifest import new_run_manifest, snapshot


class ThrottleError(Exception):
    status_code = 429


def test_retries_throttling_then_succeeds(monkeypatch):
    monkeypatch.setattr("shared.retry.time.sleep", lambda _: None)
    attempts = []
    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise ThrottleError("throttled")
        return "ok"
    assert with_retries(operation, attempts=3) == "ok"
    assert len(attempts) == 2


def test_does_not_retry_permanent_errors(monkeypatch):
    monkeypatch.setattr("shared.retry.time.sleep", lambda _: None)
    attempts = []
    def operation():
        attempts.append(1)
        raise ValueError("bad input")
    with pytest.raises(ValueError):
        with_retries(operation, attempts=3)
    assert len(attempts) == 1


def test_retry_classifier_accepts_only_transient_statuses():
    assert is_transient_error(SimpleNamespace(status_code=503))
    assert is_transient_error(SimpleNamespace(status_code=429))
    assert not is_transient_error(SimpleNamespace(status_code=403))


def test_manifest_snapshots_increment_revision():
    manifest = new_run_manifest()
    assert manifest["status"] == "running"
    assert snapshot(manifest)["manifest_revision"] == 1
    assert snapshot(manifest)["manifest_revision"] == 2


def test_manifest_accepts_a_deterministic_run_id():
    manifest = new_run_manifest("scheduled-run", previous_revision=5)
    assert manifest["run_id"] == "scheduled-run"
    assert snapshot(manifest)["manifest_revision"] == 6
