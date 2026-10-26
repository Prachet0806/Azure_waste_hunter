import os
import time

from observability.telemetry import log_event


def is_transient_error(error):
    """Retry network interruptions and Azure throttling/server errors only."""
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    if error.__class__.__name__ in {
        "ServiceRequestError", "ServiceResponseError", "ConnectTimeout", "ReadTimeout", "Timeout", "ConnectionError"
    }:
        return True
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    return status in (408, 429) or isinstance(status, int) and 500 <= status <= 599


def with_retries(fn, *, attempts=None, base_delay_ms=None, retry_exceptions=(Exception,), retry_if=is_transient_error):
    max_attempts = int(os.getenv("RETRY_MAX_ATTEMPTS", "3")) if attempts is None else attempts
    base_delay = (float(os.getenv("RETRY_BASE_DELAY_MS", "200")) if base_delay_ms is None else base_delay_ms) / 1000.0
    if max_attempts < 1:
        raise ValueError("Retry attempts must be at least one")

    last_err = None
    for i in range(max_attempts):
        try:
            return fn()
        except retry_exceptions as err:
            last_err = err
            if i == max_attempts - 1 or not retry_if(err):
                raise
            delay = base_delay * (2 ** i)
            log_event("retry", "retry_scheduled", attempt=i + 1,
                      error_type=type(err).__name__, status_code=getattr(err, "status_code", None),
                      delay_seconds=delay)
            time.sleep(delay)
    raise last_err
