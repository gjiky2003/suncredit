"""Synthetic borrower data generator for SunCredit underwriting.

Generates 1500 realistic borrower profiles and splits into train/val/test CSVs.
Runs automatically on import (idempotent — skips if files already exist).
"""
import os
import csv
import math
import random

HERE = os.path.dirname(os.path.abspath(__file__))

PURPOSES = [
    "debt_consolidation", "credit_card", "home_improvement", "medical",
    "auto", "major_purchase", "moving", "vacation", "wedding", "other",
]
HOME = ["rent", "mortgage", "own"]


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _gen_one(rng):
    age = int(_clip(rng.gauss(38, 12), 18, 75))
    # income skewed lognormal-ish
    income = float(_clip(rng.lognormvariate(math.log(55000), 0.55), 15000, 250000))
    credit_score = int(_clip(rng.gauss(680, 70), 500, 850))
    dti = float(_clip(rng.gauss(0.28, 0.12), 0.0, 0.60))
    util = float(_clip(rng.betavariate(2, 3), 0.0, 1.0))
    emp_len = float(_clip(rng.gauss(6, 5), 0, 30))
    derog = int(_clip(rng.expovariate(1.0 / 1.2), 0, 8))
    n_lines = int(_clip(rng.gauss(10, 5), 0, 30))
    home = rng.choices(HOME, weights=[0.45, 0.35, 0.20])[0]
    loan_amount = float(_clip(rng.lognormvariate(math.log(8000), 0.7), 500, 50000))
    purpose = rng.choice(PURPOSES)

    # Risk-weighted default probability
    z = (
        -3.5
        + (680 - credit_score) * 0.012
        + dti * 3.0
        + util * 1.4
        + derog * 0.35
        + (max(0, 25000 - income) / 25000) * 0.9
        + (loan_amount / 50000) * 0.6
        - min(emp_len, 10) * 0.06
        - (1 if home == "own" else 0) * 0.25
        - (1 if home == "mortgage" else 0) * 0.10
        + (1 if purpose in ("vacation", "wedding", "other") else 0) * 0.25
    )
    p = 1.0 / (1.0 + math.exp(-z))
    default = 1 if rng.random() < p else 0

    return {
        "age": age,
        "annual_income": round(income, 2),
        "credit_score": credit_score,
        "dti_ratio": round(dti, 4),
        "utilization": round(util, 4),
        "employment_length": round(emp_len, 1),
        "num_derogatory": derog,
        "num_credit_lines": n_lines,
        "home_ownership": home,
        "loan_amount": round(loan_amount, 2),
        "loan_purpose": purpose,
        "default": default,
    }


def generate(n=1500, seed=42, out_dir=HERE):
    rng = random.Random(seed)
    rows = [_gen_one(rng) for _ in range(n)]
    rng.shuffle(rows)
    n_train = int(n * 0.6)
    n_val = int(n * 0.2)
    splits = {
        "train.csv": rows[:n_train],
        "val.csv": rows[n_train:n_train + n_val],
        "test.csv": rows[n_train + n_val:],
    }
    fieldnames = list(rows[0].keys())
    for name, data in splits.items():
        path = os.path.join(out_dir, name)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(data)
    return splits


# Run on import if files don't exist
if not all(os.path.exists(os.path.join(HERE, n)) for n in ("train.csv", "val.csv", "test.csv")):
    generate()


if __name__ == "__main__":
    splits = generate()
    for k, v in splits.items():
        defaults = sum(r["default"] for r in v)
        print(f"{k}: {len(v)} rows, {defaults} defaults ({defaults/len(v):.1%})")
