"""Tag presence and basic value validation; policy-specific checks stay explicit."""

REQUIRED_TAGS = ("owner", "env", "cost-center")


def check_tags(resource: dict) -> dict:
    raw_tags = resource.get("tags")
    if raw_tags is not None and not isinstance(raw_tags, dict):
        return {"status": "unassessed", "violations": [], "reason": "Tag payload was not an object."}
    tags = {str(key).strip().casefold(): value for key, value in (raw_tags or {}).items()}
    violations = []
    for required in REQUIRED_TAGS:
        value = tags.get(required)
        if value is None:
            violations.append(f"{required}:missing")
        elif not isinstance(value, str) or not value.strip():
            violations.append(f"{required}:invalid")
    return {"status": "violations" if violations else "compliant", "violations": violations, "reason": None}
