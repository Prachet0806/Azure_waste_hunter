import logging

def log_event(component: str, message: str):
    """
    Structured logging for Azure Application Insights.
    """
    logging.info(f"[{component}] {message}")
