import os
import time


def with_retries(fn, *, attempts=None, base_delay_ms=None, retry_exceptions=(Exception,)):
    max_attempts = attempts or int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    base_delay = (base_delay_ms or float(os.getenv("RETRY_BASE_DELAY_MS", "200"))) / 1000.0

    last_err = None
    for i in range(max_attempts):
        try:
            return fn()
        except retry_exceptions as err:
            last_err = err
            if i == max_attempts - 1:
                raise
            time.sleep(base_delay * (2 ** i))
    raise last_err
