"""Pure-python logistic regression with L2 regularization (numpy-only)."""
import numpy as np


class LogisticRegression:
    """Binary logistic regression trained via batch gradient descent."""

    def __init__(self, lr=0.1, n_iter=1500, l2=0.005):
        self.lr = lr
        self.n_iter = n_iter
        self.l2 = l2
        self.w = None
        self.b = 0.0

    @staticmethod
    def _sigmoid(z):
        z = np.clip(z, -30, 30)
        return 1.0 / (1.0 + np.exp(-z))

    def fit(self, X, y):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        n, d = X.shape
        self.w = np.zeros(d)
        self.b = 0.0
        for _ in range(self.n_iter):
            p = self._sigmoid(X @ self.w + self.b)
            err = p - y
            grad_w = X.T @ err / n + self.l2 * self.w
            grad_b = err.mean()
            self.w -= self.lr * grad_w
            self.b -= self.lr * grad_b
        return self

    def predict_proba(self, X):
        X = np.asarray(X, dtype=float)
        return self._sigmoid(X @ self.w + self.b)

    def predict(self, X, thresh=0.5):
        return (self.predict_proba(X) >= thresh).astype(int)

    def to_dict(self):
        return {"w": self.w.tolist(), "b": float(self.b)}

    def from_dict(self, d):
        self.w = np.array(d["w"], dtype=float)
        self.b = float(d["b"])
        return self
