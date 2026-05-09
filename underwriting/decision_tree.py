"""Pure-python decision tree classifier with gini splits (numpy-only)."""
import numpy as np


class DecisionTree:
    """CART-style binary classifier trained on gini impurity."""

    def __init__(self, max_depth=6, min_samples_split=10, feature_indices=None):
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.feature_indices = feature_indices  # subset of features used
        self.tree = None

    @staticmethod
    def _gini(y):
        if len(y) == 0:
            return 0.0
        p = y.mean()
        return 2.0 * p * (1.0 - p)

    def _best_split(self, X, y, feat_idxs):
        n, _ = X.shape
        best = None
        best_score = self._gini(y) * n
        for j in feat_idxs:
            col = X[:, j]
            # candidate thresholds: quantiles for speed
            uniq = np.unique(col)
            if len(uniq) > 12:
                qs = np.linspace(0.1, 0.9, 9)
                thresholds = np.quantile(col, qs)
            else:
                thresholds = (uniq[:-1] + uniq[1:]) / 2.0 if len(uniq) > 1 else []
            for t in thresholds:
                left = col <= t
                nl = left.sum()
                nr = n - nl
                if nl < 5 or nr < 5:
                    continue
                score = self._gini(y[left]) * nl + self._gini(y[~left]) * nr
                if score < best_score:
                    best_score = score
                    best = (j, float(t))
        return best

    def _build(self, X, y, depth):
        # leaf
        if depth >= self.max_depth or len(y) < self.min_samples_split or y.min() == y.max():
            return {"leaf": True, "p": float(y.mean()) if len(y) else 0.5}
        feat_idxs = self.feature_indices if self.feature_indices is not None else range(X.shape[1])
        split = self._best_split(X, y, list(feat_idxs))
        if split is None:
            return {"leaf": True, "p": float(y.mean())}
        j, t = split
        left_mask = X[:, j] <= t
        return {
            "leaf": False,
            "feat": int(j),
            "thresh": float(t),
            "left": self._build(X[left_mask], y[left_mask], depth + 1),
            "right": self._build(X[~left_mask], y[~left_mask], depth + 1),
        }

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        self.tree = self._build(X, y, 0)
        return self

    def _predict_one(self, x, node):
        while not node["leaf"]:
            node = node["left"] if x[node["feat"]] <= node["thresh"] else node["right"]
        return node["p"]

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        return np.array([self._predict_one(x, self.tree) for x in X])

    def predict(self, X, thresh=0.5):
        return (self.predict_proba(X) >= thresh).astype(int)

    def to_dict(self):
        return {"max_depth": self.max_depth, "tree": self.tree}

    def from_dict(self, d):
        self.max_depth = d.get("max_depth", 6)
        self.tree = d["tree"]
        return self
