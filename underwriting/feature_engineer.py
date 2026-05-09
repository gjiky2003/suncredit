"""Feature engineering for SunCredit underwriting models.

Transforms raw borrower attributes into a numpy feature matrix suitable for ML.
"""
import math
import numpy as np

PURPOSES = [
    "debt_consolidation", "credit_card", "home_improvement", "medical",
    "auto", "major_purchase", "moving", "vacation", "wedding", "other",
]
HOME = ["rent", "mortgage", "own"]


class FeatureEngineer:
    """Fit/transform raw borrower dicts → numeric feature matrix."""

    NUMERIC = [
        "age", "annual_income", "credit_score", "dti_ratio", "utilization",
        "employment_length", "num_derogatory", "num_credit_lines", "loan_amount",
    ]

    def __init__(self):
        self.means = None
        self.stds = None
        self.feature_names = None

    def _row_features(self, r):
        income = float(r.get("annual_income", 0)) or 1.0
        n_lines = float(r.get("num_credit_lines", 0)) or 1.0
        emp = float(r.get("employment_length", 0))
        dti = float(r.get("dti_ratio", 0))
        util = float(r.get("utilization", 0))
        derog = float(r.get("num_derogatory", 0))

        engineered = [
            math.log(max(income, 1.0)),
            income / max(n_lines, 1.0),
            dti * util,
            min(emp / 10.0, 1.0),  # employment stability (capped)
            derog / max(n_lines, 1.0),  # derogatory density
        ]
        numeric = [float(r.get(k, 0) or 0) for k in self.NUMERIC]

        home = r.get("home_ownership", "rent")
        home_oh = [1.0 if home == h else 0.0 for h in HOME]

        purpose = r.get("loan_purpose", "other")
        purpose_oh = [1.0 if purpose == p else 0.0 for p in PURPOSES]

        return numeric + engineered + home_oh + purpose_oh

    def _names(self):
        return (
            list(self.NUMERIC)
            + ["log_income", "income_per_line", "dti_x_util", "emp_stability", "derog_density"]
            + [f"home_{h}" for h in HOME]
            + [f"purpose_{p}" for p in PURPOSES]
        )

    def fit(self, rows):
        X = np.array([self._row_features(r) for r in rows], dtype=float)
        self.means = X.mean(axis=0)
        self.stds = X.std(axis=0)
        self.stds[self.stds < 1e-8] = 1.0
        # only standardize the first len(NUMERIC)+5 continuous columns
        self.n_continuous = len(self.NUMERIC) + 5
        self.feature_names = self._names()
        return self

    def transform(self, rows):
        X = np.array([self._row_features(r) for r in rows], dtype=float)
        if self.means is not None:
            n = self.n_continuous
            X[:, :n] = (X[:, :n] - self.means[:n]) / self.stds[:n]
        return X

    def fit_transform(self, rows):
        self.fit(rows)
        return self.transform(rows)

    def to_dict(self):
        return {
            "means": self.means.tolist() if self.means is not None else None,
            "stds": self.stds.tolist() if self.stds is not None else None,
            "n_continuous": getattr(self, "n_continuous", len(self.NUMERIC) + 5),
            "feature_names": self._names(),
        }

    def from_dict(self, d):
        self.means = np.array(d["means"]) if d.get("means") else None
        self.stds = np.array(d["stds"]) if d.get("stds") else None
        self.n_continuous = d.get("n_continuous", len(self.NUMERIC) + 5)
        self.feature_names = d.get("feature_names", self._names())
        return self
