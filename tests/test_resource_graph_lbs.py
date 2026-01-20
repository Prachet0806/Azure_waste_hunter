from scanner import resource_graph as rg


def test_normalize_lb_sets_type_and_tags():
    resources = [{"id": "lb-1", "tags": {"owner": "finops"}}]
    normalized = rg._normalize(resources, "lb")

    assert normalized[0]["type"] == "lb"
    assert normalized[0]["tags"]["owner"] == "finops"
