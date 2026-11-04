"""P5 selector: generator, features, labelling, grouped CV and explanation (API tests: test_plans_api.py)."""
import math

import numpy as np
import pandas as pd
import pytest
from app.selector import model as M
from app.selector.dataset import ENGINES, label_cases, plan_cases, regret_pct
from app.selector.features import FEATURE_NAMES, extract_features
from app.selector.generator import FAMILIES, TIGHTNESS, generate_family_instance


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("tightness", list(TIGHTNESS))
def test_generated_instances_are_valid_synthetic_and_reproducible(family, tightness):
    a = generate_family_instance(family, 30, tightness, seed=1)
    b = generate_family_instance(family, 30, tightness, seed=1)
    a.validate()  # every customer reachable on a direct trip, capacity fits
    assert a.instance_id == b.instance_id
    assert a.source == "synthetic" and "synthetic" in a.name
    assert a.has_time_windows == (tightness != "none")
    assert generate_family_instance(family, 30, tightness, seed=2).instance_id != a.instance_id


def test_features_reflect_tightness_budget_and_clustering():
    loose = extract_features(generate_family_instance("uniform", 40, "loose", 0), 3.0)
    tight = extract_features(generate_family_instance("uniform", 40, "tight", 0), 1.0)
    plain = extract_features(generate_family_instance("uniform", 40, "none", 0), 1.0)
    assert set(loose) == set(FEATURE_NAMES)
    assert tight["tw_width_rel_mean"] < loose["tw_width_rel_mean"]
    assert tight["tw_tight_share"] > 0.9 and loose["tw_tight_share"] < 0.1
    assert plain["has_tw"] == 0 and plain["tw_width_rel_mean"] == 0
    assert loose["budget_s"] == 3.0 and math.isclose(tight["budget_per_customer_ms"], 25.0)
    clustered = extract_features(generate_family_instance("clustered", 40, "none", 0), 1.0)
    assert clustered["nn_dist_rel"] < plain["nn_dist_rel"]


def test_plan_cases_grid():
    cases = plan_cases([20, 50], ["none", "tight"], [1.0, 3.0], seeds=2)
    assert len(cases) == 3 * 2 * 2 * 2 * 2
    assert len({c["case_id"] for c in cases}) == len(cases)


def _raw(rows):
    """rows: (case_id, family, engine, feasible, distance)."""
    base = {f"f_{n}": 1.0 for n in FEATURE_NAMES}
    return pd.DataFrame([{"case_id": c, "family": f, "n_customers": 20, "tightness": "none", "budget_s": 1.0,
                          "engine": e, "feasible": ok, "total_distance": d, **base} for c, f, e, ok, d in rows])


def test_labelling_ties_go_to_ortools_and_infeasible_runs_never_win():
    raw = _raw([("c1", "uniform", "ortools", True, 100.0), ("c1", "uniform", "hybrid", True, 100.0),
                ("c1", "uniform", "ga_ls", True, 120.0),
                ("c2", "uniform", "ortools", False, 50.0), ("c2", "uniform", "hybrid", True, 110.0),
                ("c2", "uniform", "ga_ls", True, 105.0),
                ("c3", "uniform", "ortools", False, math.nan), ("c3", "uniform", "hybrid", False, math.nan),
                ("c3", "uniform", "ga_ls", False, math.nan)])
    cases = label_cases(raw).set_index("case_id")
    assert cases.loc["c1", "label"] == "ortools"
    assert cases.loc["c2", "label"] == "ga_ls"  # the infeasible 50.0 is ignored
    assert cases.loc["c3", "label"] == "none_feasible"
    assert math.isinf(regret_pct(cases.loc["c2"], "ortools"))
    assert math.isclose(regret_pct(cases.loc["c2"], "hybrid"), 100 * 5 / 105)


def _fake_cases(n_per_family=12):
    """Cases where the best engine depends only on has_tw (a learnable rule), for CV mechanics."""
    rng = np.random.default_rng(0)
    rows = []
    for fam in FAMILIES:
        for k in range(n_per_family):
            tw = k % 2
            feats = {f"f_{n}": float(rng.uniform()) for n in FEATURE_NAMES}
            feats["f_has_tw"] = float(tw)
            d = {"dist_ortools": 100.0 if tw else 110.0, "dist_hybrid": 105.0, "dist_ga_ls": 120.0 if tw else 100.0}
            rows.append({"case_id": f"{fam}{k}", "family": fam, "n_customers": 20 + 30 * (k % 3), "budget_s": 1.0,
                         **feats, **d, "best_dist": 100.0, "label": "ortools" if tw else "ga_ls"})
    return pd.DataFrame(rows)


def test_grouped_cv_holds_out_each_family_and_reports_baselines():
    ev = M.evaluate(_fake_cases(), "family")
    assert [f["held_out"] for f in ev["folds"]] == sorted(FAMILIES)
    assert ev["selector"]["accuracy"] == 1.0 and ev["selector"]["mean_regret_pct"] == 0.0
    assert ev["always_ortools"]["accuracy"] == 0.5
    assert math.isclose(ev["always_ortools"]["mean_regret_pct"], 5.0)
    assert ev["oracle"]["mean_regret_pct"] == 0.0
    assert 0.0 < ev["random"]["accuracy"] < 1.0
    assert set(ENGINES) <= {k.removeprefix("always_") for k in ev}


def test_selector_explains_choice_and_flags_extrapolation(tmp_path):
    path = tmp_path / "cases.csv"
    _fake_cases().to_csv(path, index=False)
    sel = M.EngineSelector(path)
    inst = generate_family_instance("uniform", 200, "tight", 0)
    s = sel.choose(inst, 30.0).to_dict()
    assert s["engine"] == "ortools" and s["method"] == "model"
    assert "has_tw" in s["explanation"] and "synthetic" in s["explanation"]
    assert "outside the training range" in s["explanation"]
    assert s["details"]["outside_training_range"]


def test_selector_falls_back_to_ortools_without_data_and_says_so(tmp_path):
    s = M.EngineSelector(tmp_path / "missing.csv").choose(generate_family_instance("mixed", 20, "none", 0), 1.0)
    assert s.engine == "ortools" and s.method == "fallback"
    assert "fell back" in s.explanation


def test_committed_training_data_trains_a_model():
    if not M.DATA_PATH.exists():
        pytest.skip("selector training data not built yet")
    sel = M.EngineSelector()
    assert sel.model is not None
    s = sel.choose(generate_family_instance("clustered", 50, "loose", 7), 3.0)
    assert s.engine in ENGINES
