from compliance.tag_checker import check_tags


def test_tag_keys_are_case_insensitive_and_values_must_be_nonempty():
    result = check_tags({"tags": {"OWNER": "ops", "Env": "prod", "Cost-Center": "123"}})
    assert result["status"] == "compliant"
    assert result["violations"] == []


def test_missing_and_blank_tags_are_separately_reported():
    result = check_tags({"tags": {"owner": " ", "env": "prod"}})
    assert result["status"] == "violations"
    assert "owner:invalid" in result["violations"]
    assert "cost-center:missing" in result["violations"]


def test_malformed_tag_payload_is_unassessed():
    assert check_tags({"tags": "not-an-object"})["status"] == "unassessed"
