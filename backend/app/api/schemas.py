"""Pydantic request schemas. Domain rules (positive demands, capacity fit, ...)
live in Instance.validate(); these schemas only enforce shape and sane bounds."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Metric = Literal["euclidean", "haversine", "euclidean_nint", "euclidean_trunc1"]


class CustomerIn(BaseModel):
    id: int
    x: float
    y: float
    demand: int
    # Optional time window: service must start within [ready_time, due_time].
    ready_time: float = Field(0.0, ge=0)
    due_time: float | None = Field(None, ge=0)
    service_time: float = Field(0.0, ge=0)


class InstanceIn(BaseModel):
    name: str = ""
    metric: Metric = "haversine"
    distance_unit: str = "km"
    depot_x: float
    depot_y: float
    customers: list[CustomerIn] = Field(max_length=1000)
    vehicle_count: int
    vehicle_capacity: int
    fixed_vehicle_cost: float = Field(50.0, ge=0)
    cost_per_distance: float = Field(1.0, ge=0)
    depot_ready_time: float = Field(0.0, ge=0)
    depot_due_time: float | None = Field(None, ge=0)
    time_per_distance: float = Field(1.0, gt=0)
    time_unit: str = "min"


class GenerateIn(BaseModel):
    n_customers: int = Field(ge=1, le=1000)
    seed: int = 0
    metric: Metric = "haversine"
    demand_min: int = Field(1, ge=1)
    demand_max: int = Field(10, ge=1)
    vehicle_capacity: int | None = Field(None, ge=1)
    vehicle_count: int | None = Field(None, ge=1)
    fixed_vehicle_cost: float = Field(50.0, ge=0)
    cost_per_distance: float = Field(1.0, ge=0)


class ORToolsParams(BaseModel):
    # None = audited default for the problem type and time budget (docs/decisions/0005).
    first_solution: Literal["PATH_CHEAPEST_ARC", "PARALLEL_CHEAPEST_INSERTION", "SAVINGS",
                            "LOCAL_CHEAPEST_INSERTION"] | None = None
    metaheuristic: Literal["GUIDED_LOCAL_SEARCH", "SIMULATED_ANNEALING", "TABU_SEARCH",
                           "GREEDY_DESCENT"] | None = None


class GAParams(BaseModel):
    population_size: int = Field(100, ge=4, le=2000)
    max_generations: int = Field(500, ge=1, le=1_000_000)
    stagnation_generations: int | None = Field(100, ge=1)
    elite_count: int = Field(2, ge=0)
    tournament_size: int = Field(3, ge=1)
    crossover_rate: float = Field(0.9, ge=0, le=1)
    mutation_rate: float = Field(0.2, ge=0, le=1)
    nn_seed_fraction: float = Field(0.1, ge=0, le=1)
    due_seed_fraction: float = Field(0.1, ge=0, le=1)
    lateness_weight: float | None = Field(None, ge=0)
    tw_repair: bool = True
    seed: int = 0


class RunIn(BaseModel):
    instance_id: str
    algorithm: Literal["ortools", "ga"]
    time_limit_s: float | None = Field(None, gt=0)  # OR-Tools default 10 s; GA: optional extra stop
    ortools: ORToolsParams = ORToolsParams()
    ga: GAParams = GAParams()


class ExperimentIn(BaseModel):
    """Fair comparison on one instance: same wall-clock budget for every run."""
    instance_id: str
    time_budget_s: float = Field(10.0, gt=0)
    ga_seeds: int = Field(5, ge=1, le=50)
    ortools_repeats: int = Field(1, ge=1, le=10)
    ga: GAParams = GAParams()
    ortools: ORToolsParams = ORToolsParams()
