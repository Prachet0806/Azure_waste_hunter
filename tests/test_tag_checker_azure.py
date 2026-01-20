from compliance.tag_checker import check_tags

def test_tag_compliance():
    resource = {"type": "vm", "id": "vm-1", "tags": {"owner": "sre", "env": "prod"}}
    missing = check_tags(resource)

    assert "cost-center" in missing
