# compliance/tag_checker.py
REQUIRED_TAGS = ["owner", "env", "cost-center"]

def check_tags(resource: dict) -> list[str]:
    """
    Returns a list of missing required tags for a resource.
    Empty list means compliant.
    """
    tags = resource.get("tags", {}) or {}
    return [t for t in REQUIRED_TAGS if t not in tags]
