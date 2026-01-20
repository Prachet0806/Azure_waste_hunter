from cost_engine.estimator import estimate_cost


def test_estimate_cost_static_vm():
    resource = {"type": "vm", "vm_size": "Standard_B2s"}
    assert estimate_cost(resource) == 36.0


def test_estimate_cost_static_disk():
    resource = {"type": "disk", "sku": "Standard_LRS", "size_gb": 10}
    assert estimate_cost(resource) == 0.5
