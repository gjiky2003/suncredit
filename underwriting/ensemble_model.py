"""Weighted ensemble of LR + DT + RF for SunCredit underwriting."""
import numpy as np
from underwriting.logistic_regression import LogisticRegression
from underwriting.decision_tree import DecisionTree
from underwriting.random_forest import RandomForest


class EnsembleModel:
    """Blends predict_proba of three base learners with fixed weights."""

    def __init__(self, weights=(0.3, 0.3, 0.4)):
        self.weights = tuple(weights)
        self.lr = LogisticRegression()
        self.dt = DecisionTree(max_depth=6)
        self.rf = RandomForest(n_trees=50, max_depth=6)

    def fit(self, X, y):
        self.lr.fit(X, y)
        self.dt.fit(X, y)
        self.rf.fit(X, y)
        return self

    def predict_proba(self, X):
        wlr, wdt, wrf = self.weights
        return (
            wlr * self.lr.predict_proba(X)
            + wdt * self.dt.predict_proba(X)
            + wrf * self.rf.predict_proba(X)
        )

    def predict(self, X, thresh=0.5):
        return (self.predict_proba(X) >= thresh).astype(int)

    def to_dict(self):
        return {
            "weights": list(self.weights),
            "lr": self.lr.to_dict(),
            "dt": self.dt.to_dict(),
            "rf": self.rf.to_dict(),
        }

    def from_dict(self, d):
        self.weights = tuple(d.get("weights", (0.3, 0.3, 0.4)))
        self.lr = LogisticRegression().from_dict(d["lr"])
        self.dt = DecisionTree().from_dict(d["dt"])
        self.rf = RandomForest().from_dict(d["rf"])
        return self
