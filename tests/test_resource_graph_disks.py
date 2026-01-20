from scanner import resource_graph as rg


def test_normalize_disks_sets_type_and_tags():
    resources = [{"id": "disk-1", "tags": None, "size_gb": 10, "sku": "Premium_LRS"}]
    normalized = rg._normalize(resources, "disk")

    assert normalized[0]["type"] == "disk"
    assert normalized[0]["tags"] == {}
    assert normalized[0]["sku"] == "Premium_LRS"
