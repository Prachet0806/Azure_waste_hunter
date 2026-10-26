import json
import logging


def log_event(component: str, event: str, **dimensions):
    """Emit queryable fields; keep metric cardinality out of this logger."""
    fields = {"component": component, "event": event, **dimensions}
    logging.info(json.dumps(fields, sort_keys=True), extra={"custom_dimensions": fields})
