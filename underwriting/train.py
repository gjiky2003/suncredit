"""Train all SunCredit underwriting models and save weights to JSON.

Run:  python3 train.py
"""
import os
import csv
import json
import time
import numpy as np

import data_generator  # noqa: F401  — generates CSVs on import if missing
from underwriting.feature_engineer import FeatureEngineer
from underwriting.ensemble_model import EnsembleModel

HERE = os.path.dirname(os.path.abspath(__file__))


def load_csv(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    # cast numeric fields
    num_keys = ["age", "annual_income", "credit_score", "dti_ratio", "utilization",
                "employment_length", "num_derogatory", "num_credit_lines", "loan_amount", "default"]
    for r in rows:
        for k in num_keys:
            if k in r:
                r[k] = float(r[k])
    return rows


def auc(y_true, y_score):
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    # Mann-Whitney U
    n_pos, n_neg = len(pos), len(neg)
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(n_pos + n_neg)
    ranks[order] = np.arange(1, n_pos + n_neg + 1)
    sum_ranks_pos = ranks[:n_pos].sum()
    u = sum_ranks_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def feature_importance_from_lr(lr, names):
    imp = np.abs(lr.w)
    if imp.sum() > 0:
        imp = imp / imp.sum()
    return {n: float(v) for n, v in zip(names, imp)}


def main():
    train_rows = load_csv(os.path.join(HERE, "train.csv"))
    val_rows = load_csv(os.path.join(HERE, "val.csv"))

    fe = FeatureEngineer()
    X_train = fe.fit_transform(train_rows)
    y_train = np.array([r["default"] for r in train_rows])
    X_val = fe.transform(val_rows)
    y_val = np.array([r["default"] for r in val_rows])

    print(f"Train: {len(train_rows)} rows ({int(y_train.sum())} defaults)")
    print(f"Val:   {len(val_rows)} rows ({int(y_val.sum())} defaults)")

    t0 = time.time()
    model = EnsembleModel(weights=(0.5, 0.15, 0.35))
    model.fit(X_train, y_train)
    print(f"Training took {time.time()-t0:.1f}s")

    # Per-model AUCs
    p_lr = model.lr.predict_proba(X_val)
    p_dt = model.dt.predict_proba(X_val)
    p_rf = model.rf.predict_proba(X_val)
    p_ens = model.predict_proba(X_val)

    auc_lr = auc(y_val, p_lr)
    auc_dt = auc(y_val, p_dt)
    auc_rf = auc(y_val, p_rf)
    auc_ens = auc(y_val, p_ens)

    print(f"Val AUC — LR: {auc_lr:.3f}  DT: {auc_dt:.3f}  RF: {auc_rf:.3f}  Ensemble: {auc_ens:.3f}")

    fi = feature_importance_from_lr(model.lr, fe.feature_names)

    bundle = {
        "feature_engineer": fe.to_dict(),
        "ensemble": model.to_dict(),
        "feature_importance": fi,
        "auc_scores": {
            "lr": float(auc_lr),
            "dt": float(auc_dt),
            "rf": float(auc_rf),
            "ensemble": float(auc_ens),
        },
    }
    out = os.path.join(HERE, "model_weights.json")
    with open(out, "w") as f:
        json.dump(bundle, f)

    print(f"Model trained, AUC: {auc_ens:.2f}, weights saved")
    return auc_ens


if __name__ == "__main__":
    main()
