import os
import tempfile

# Keep the module-level `app` in app.main from writing into the repo during tests.
os.environ.setdefault("ROUTEOPT_DATA_DIR", tempfile.mkdtemp(prefix="routeopt_test_"))
# Test clients poll plans many times a second; the rate limiter has its own tests with small limits.
os.environ.setdefault("LOGIMIND_RATE_PER_MIN", "1000000")
os.environ.setdefault("LOGIMIND_RATE_BURST", "100000")

import pytest
from app.models.problem import Customer, Instance


@pytest.fixture
def tiny() -> Instance:
    """4 customers, capacity 4, 2 vehicles, no fixed cost, Euclidean.
    Hand-checked optimum: {1,2} and {3,4} = (3+4+5) + (3+4+5) = 24.
    """
    return Instance(
        depot_x=0, depot_y=0,
        customers=[Customer(1, 3, 0, 2), Customer(2, 3, 4, 2), Customer(3, -3, 0, 2), Customer(4, -3, -4, 2)],
        vehicle_count=2, vehicle_capacity=4, metric="euclidean",
        fixed_vehicle_cost=0.0, cost_per_distance=1.0, name="tiny")
