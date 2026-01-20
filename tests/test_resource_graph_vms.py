from scanner import resource_graph as rg


def test_normalize_vm_sets_type_and_vm_size():
    resources = [{"id": "vm-1", "tags": {}, "vmSize": "Standard_B2s"}]
    normalized = rg._normalize(resources, "vm")

    assert normalized[0]["type"] == "vm"
    assert normalized[0]["vm_size"] == "Standard_B2s"
