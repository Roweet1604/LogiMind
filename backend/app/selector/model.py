"""Engine picker: a small decision tree over instance features + budget.

Trained on the committed SYNTHETIC dataset (`data/training_cases.csv`, built by
experiments/selector_dataset.py). Training is deterministic (random_state=0) and
takes milliseconds, so the model is fitted from the CSV on first use instead of
committing a pickle. If the dataset is missing, `engine=auto` falls back to OR-Tools
and says so.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from app.models.problem import Instance
from app.selector.dataset import ENGINES, regret_pct
from app.selector.features import FEATURE_NAMES, extract_features, feature_vector

DATA_PATH = Path(__file__).resolve().parent / "data" / "training_cases.csv"
FALLBACK_ENGINE = "ortools"
TREE_PARAMS = {"max_depth": 3, "min_samples_leaf": 4, "random_state": 0}
ENGINE_LABELS = {"ortools": "OR-Tools (audited defaults)", "hybrid": "Hybrid (OR-Tools seed + GA with local search)",
                 "ga_ls": "GA with local search"}


def _xy(cases: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    usable = cases[cases["label"].isin(ENGINES)]
    return usable[[f"f_{n}" for n in FEATURE_NAMES]].to_numpy(float), usable["label"].to_numpy()


def fit(cases: pd.DataFrame) -> DecisionTreeClassifier:
    x, y = _xy(cases)
    return DecisionTreeClassifier(**TREE_PARAMS).fit(x, y)


REGRESSOR_PARAMS = {"max_depth": 3, "min_samples_leaf": 4, "random_state": 0}


class RegretModel:
    """One small regression tree per engine predicting that engine's regret %; picks the lowest.
    Added after the classifier's first CV result (see docs/model_card_selector.md)."""

    def __init__(self, cases: pd.DataFrame):
        usable = cases[cases["label"].isin(ENGINES)]
        x = usable[[f"f_{n}" for n in FEATURE_NAMES]].to_numpy(float)
        self.trees = {}
        for e in ENGINES:
            y = np.array([regret_pct(c, e) for _, c in usable.iterrows()])
            y = np.where(np.isfinite(y), y, 100.0)  # a failed run counts as 100% regret for training
            self.trees[e] = DecisionTreeRegressor(**REGRESSOR_PARAMS).fit(x, y)

    def predicted_regrets(self, x: np.ndarray) -> dict[str, np.ndarray]:
        return {e: t.predict(x) for e, t in self.trees.items()}

    def predict(self, x: np.ndarray) -> list[str]:
        pr = self.predicted_regrets(x)
        return [min(ENGINES, key=lambda e: (pr[e][i], ENGINES.index(e))) for i in range(len(x))]


def _score(cases: pd.DataFrame, chosen: list[str]) -> dict[str, Any]:
    regrets = [regret_pct(c, e) for (_, c), e in zip(cases.iterrows(), chosen)]
    finite = [r for r in regrets if math.isfinite(r)]
    return {
        "cases": len(cases),
        "accuracy": float(np.mean([e == lab for e, lab in zip(chosen, cases["label"])])) if len(cases) else math.nan,
        "failures": len(regrets) - len(finite),  # chosen engine had no feasible plan
        "mean_regret_pct": float(np.mean(finite)) if finite else math.nan,
        "max_regret_pct": float(np.max(finite)) if finite else math.nan,
    }


def evaluate(cases: pd.DataFrame, group_col: str = "family", random_repeats: int = 200) -> dict[str, Any]:
    """Leave-one-group-out CV for the tree; baselines scored on the same held-out cases."""
    cases = cases[cases["label"].isin(ENGINES)].reset_index(drop=True)
    predicted = [""] * len(cases)
    predicted_regret = [""] * len(cases)
    folds = []
    for group in sorted(cases[group_col].unique()):
        test = cases[group_col] == group
        model = fit(cases[~test])
        x, _ = _xy(cases[test])
        for idx, p in zip(cases.index[test], model.predict(x)):
            predicted[idx] = str(p)
        if (~test).sum() >= 2 * REGRESSOR_PARAMS["min_samples_leaf"]:
            for idx, p in zip(cases.index[test], RegretModel(cases[~test]).predict(x)):
                predicted_regret[idx] = p
        folds.append({"held_out": str(group), **_score(cases[test], [predicted[i] for i in cases.index[test]])})
    out = {"group_col": group_col, "folds": folds, "selector": _score(cases, predicted)}
    if all(predicted_regret):
        out["selector_regret_model"] = _score(cases, predicted_regret)
    for e in ENGINES:
        out[f"always_{e}"] = _score(cases, [e] * len(cases))
    out["oracle"] = _score(cases, list(cases["label"]))
    rng = random.Random(0)
    runs = [_score(cases, [rng.choice(ENGINES) for _ in range(len(cases))]) for _ in range(random_repeats)]
    out["random"] = {k: float(np.mean([r[k] for r in runs])) for k in ("accuracy", "failures", "mean_regret_pct")}
    out["random"]["cases"] = len(cases)
    out["random"]["note"] = f"mean of {random_repeats} seeded random draws"
    out["label_counts"] = cases["label"].value_counts().to_dict()
    return out


def explain_path(model: DecisionTreeClassifier | DecisionTreeRegressor, x: np.ndarray) -> list[str]:
    tree = model.tree_
    node_ids = model.decision_path(x.reshape(1, -1)).indices
    steps = []
    for node in node_ids:
        if tree.children_left[node] == tree.children_right[node]:  # leaf
            continue
        name, thr = FEATURE_NAMES[tree.feature[node]], tree.threshold[node]
        val = x[tree.feature[node]]
        steps.append(f"{name} = {val:.3g} {'<=' if val <= thr else '>'} {thr:.3g}")
    return steps


@dataclass
class Selection:
    engine: str
    method: str  # "model" or "fallback"
    explanation: str
    features: dict[str, float]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"engine": self.engine, "engine_label": ENGINE_LABELS[self.engine], "method": self.method,
                "explanation": self.explanation, "features": self.features, "details": self.details}


class EngineSelector:
    """Serves engine=auto with the regret model (lowest leave-one-family-out regret, see the model card)."""

    def __init__(self, data_path: Path = DATA_PATH):
        self.data_path = data_path
        self.model: RegretModel | None = None
        self.cases: pd.DataFrame | None = None
        if data_path.exists():
            self.cases = pd.read_csv(data_path)
            if self.cases["label"].isin(ENGINES).sum() >= 2 * REGRESSOR_PARAMS["min_samples_leaf"]:
                self.model = RegretModel(self.cases)

    def choose(self, instance: Instance, budget_s: float) -> Selection:
        feats = extract_features(instance, budget_s)
        if self.model is None:
            return Selection(FALLBACK_ENGINE, "fallback",
                             f"No trained selector is available ({self.data_path.name} missing or too small), "
                             f"so engine=auto fell back to OR-Tools with its audited defaults.", feats, {})
        x = np.array(feature_vector(feats), dtype=float).reshape(1, -1)
        engine = self.model.predict(x)[0]
        predicted = {e: round(float(v[0]), 2) for e, v in self.model.predicted_regrets(x).items()}
        steps = explain_path(self.model.trees[engine], x[0])
        n_lo, n_hi = self.cases["n_customers"].min(), self.cases["n_customers"].max()
        b_lo, b_hi = self.cases["budget_s"].min(), self.cases["budget_s"].max()
        outside = []
        if not n_lo <= feats["n_customers"] <= n_hi:
            outside.append(f"{int(feats['n_customers'])} customers (trained on {n_lo}-{n_hi})")
        if not b_lo <= budget_s <= b_hi:
            outside.append(f"a {budget_s:g} s budget (trained on {b_lo:g}-{b_hi:g} s)")
        pred_text = ", ".join(f"{ENGINE_LABELS[e]} {v:.2f}%" for e, v in predicted.items())
        text = (f"Chose {ENGINE_LABELS[engine]} because it has the lowest predicted extra distance over the best "
                f"engine for instances like this one ({pred_text}).")
        if steps:
            text += " Rule used for the chosen engine: " + "; ".join(steps) + "."
        if outside:
            text += " Caution: this instance is outside the training range: " + ", ".join(outside) + "."
        text += (" These are predictions from synthetic training instances, not measurements on this instance; "
                 "see docs/model_card_selector.md.")
        return Selection(engine, "model", text, feats,
                         {"predicted_regret_pct": predicted, "rule": steps, "outside_training_range": outside,
                          "training_cases": int(len(self.cases)), "model": "per-engine regret trees (depth 3)"})


_SELECTOR: EngineSelector | None = None


def get_selector() -> EngineSelector:
    global _SELECTOR
    if _SELECTOR is None:
        _SELECTOR = EngineSelector()
    return _SELECTOR
