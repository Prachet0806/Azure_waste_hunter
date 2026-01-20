from scanner import resource_graph as rg


def test_normalize_postgres_sets_type_and_tags():
    resources = [{"id": "db-1", "tags": {"env": "prod"}}]
    normalized = rg._normalize(resources, "postgres")

    assert normalized[0]["type"] == "postgres"
    assert normalized[0]["tags"]["env"] == "prod"
