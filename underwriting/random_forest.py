"""Pure-python random forest using DecisionTree base learners."""
import math
import numpy as np
from underwriting.decision_tree import DecisionTree


class RandomForest:
    """Bootstrap-aggregated trees with sqrt(n) feature subsampling."""

    def __init__(self, n_trees=50, max_depth=8, seed=42):
        self.n_trees = n_trees
        self.max_depth = max_depth
        self.seed = seed
        self.trees = []  # list of (DecisionTree, feature_indices)

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        rng = np.random.RandomState(self.seed)
        n, d = X.shape
        n_feats = max(1, int(math.sqrt(d)))
        self.trees = []
        for _ in range(self.n_trees):
            idx = rng.randint(0, n, size=n)
            feats = rng.choice(d, size=n_feats, replace=False)
            t = DecisionTree(max_depth=self.max_depth, feature_indices=list(feats))
            t.fit(X[idx], y[idx])
            self.trees.append((t, feats.tolist()))
        return self

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        preds = np.zeros(X.shape[0])
        for t, _ in self.trees:
            preds += t.predict_proba(X)
        return preds / max(len(self.trees), 1)

    def predict(self, X, thresh=0.5):
        return (self.predict_proba(X) >= thresh).astype(int)

    def to_dict(self):
        return {
            "n_trees": self.n_trees,
            "max_depth": self.max_depth,
            "trees": [{"tree": t.to_dict(), "feats": f} for t, f in self.trees],
        }

    def from_dict(self, d):
        self.n_trees = d.get("n_trees", 50)
        self.max_depth = d.get("max_depth", 6)
        self.trees = []
        for entry in d["trees"]:
            t = DecisionTree(max_depth=self.max_depth)
            t.from_dict(entry["tree"])
            self.trees.append((t, entry["feats"]))
        return self
