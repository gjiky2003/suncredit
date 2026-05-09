"""Cash-flow analyzer for SunCredit thin-file underwriting.

Consumes a list of bank transactions and produces a 0-100 cash flow score
plus rich diagnostics. Also generates demo transaction streams for 5 archetypes.
"""
import math
import random
from collections import Counter
from datetime import datetime, timedelta


def _parse_date(d):
    if isinstance(d, datetime):
        return d
    return datetime.strptime(d[:10], "%Y-%m-%d")


class CashFlowAnalyzer:
    """Analyze bank transactions → cash flow signals + composite score."""

    def analyze(self, transactions):
        if not transactions:
            return self._empty()

        txns = sorted(transactions, key=lambda t: _parse_date(t["date"]))
        first = _parse_date(txns[0]["date"])
        last = _parse_date(txns[-1]["date"])
        days = max((last - first).days, 1)
        months = max(days / 30.0, 1.0)

        deposits = [t for t in txns if float(t["amount"]) > 0]
        debits = [t for t in txns if float(t["amount"]) < 0]

        # Monthly deposit aggregation
        monthly = {}
        for t in deposits:
            d = _parse_date(t["date"])
            key = (d.year, d.month)
            monthly[key] = monthly.get(key, 0.0) + float(t["amount"])
        monthly_vals = list(monthly.values()) or [0.0]
        avg_monthly_deposits = sum(monthly_vals) / len(monthly_vals)
        if len(monthly_vals) > 1 and avg_monthly_deposits > 0:
            mean = avg_monthly_deposits
            var = sum((v - mean) ** 2 for v in monthly_vals) / len(monthly_vals)
            income_volatility = math.sqrt(var) / mean
        else:
            income_volatility = 0.0

        # Paycheck regularity: look at gaps between large recurring deposits
        big_deps = [t for t in deposits if float(t["amount"]) >= 500]
        if len(big_deps) >= 3:
            dates = [_parse_date(t["date"]) for t in big_deps]
            gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            gm = sum(gaps) / len(gaps)
            gv = sum((g - gm) ** 2 for g in gaps) / len(gaps)
            cv = math.sqrt(gv) / gm if gm > 0 else 1.0
            paycheck_regularity = max(0.0, min(100.0, 100.0 * (1.0 - cv)))
        else:
            paycheck_regularity = 30.0 if big_deps else 10.0

        # Recurring bills: same-magnitude debits within categories that repeat
        cat_counts = Counter(t.get("category", "other") for t in debits)
        recurring_bill_count = sum(1 for c, n in cat_counts.items() if n >= 2 and c not in ("other",))

        overdraft_count = sum(1 for t in txns if t.get("category") == "overdraft")
        nsf_count = sum(1 for t in txns if t.get("category") == "nsf")

        # Running balance approximation (assume start = 0)
        bal = 0.0
        daily_min = {}
        for t in txns:
            bal += float(t["amount"])
            d = _parse_date(t["date"]).date()
            daily_min[d] = min(daily_min.get(d, bal), bal)
        min_daily_balance = min(daily_min.values()) if daily_min else 0.0

        total_expenses = abs(sum(float(t["amount"]) for t in debits))
        total_income = sum(float(t["amount"]) for t in deposits)
        expense_to_income_ratio = (total_expenses / total_income) if total_income > 0 else 1.5

        # Composite score
        balance_score = max(0.0, min(100.0, 50.0 + min_daily_balance / 50.0))  # $0 → 50, $2500 → 100
        overdraft_penalty = max(0.0, 100.0 - (overdraft_count + nsf_count) * 20.0)
        income_stability = max(0.0, min(100.0, 100.0 - income_volatility * 150.0)) * 0.5 + paycheck_regularity * 0.5
        if expense_to_income_ratio <= 0.7:
            expense_score = 100.0
        elif expense_to_income_ratio >= 1.2:
            expense_score = 0.0
        else:
            expense_score = (1.2 - expense_to_income_ratio) / 0.5 * 100.0

        cash_flow_score = (
            0.20 * balance_score
            + 0.20 * overdraft_penalty
            + 0.30 * income_stability
            + 0.30 * expense_score
        )
        cash_flow_score = max(0.0, min(100.0, cash_flow_score))

        return {
            "avg_monthly_deposits": round(avg_monthly_deposits, 2),
            "income_volatility": round(income_volatility, 4),
            "paycheck_regularity": round(paycheck_regularity, 1),
            "recurring_bill_count": int(recurring_bill_count),
            "overdraft_count": int(overdraft_count),
            "nsf_count": int(nsf_count),
            "min_daily_balance": round(min_daily_balance, 2),
            "expense_to_income_ratio": round(expense_to_income_ratio, 3),
            "cash_flow_score": round(cash_flow_score, 1),
        }

    def _empty(self):
        return {
            "avg_monthly_deposits": 0.0, "income_volatility": 0.0, "paycheck_regularity": 0.0,
            "recurring_bill_count": 0, "overdraft_count": 0, "nsf_count": 0,
            "min_daily_balance": 0.0, "expense_to_income_ratio": 0.0, "cash_flow_score": 0.0,
        }

    def generate_demo_transactions(self, profile):
        """Return 90 days of realistic transactions for one of 5 archetypes."""
        rng = random.Random(hash(profile) & 0xFFFFFFFF)
        start = datetime.now() - timedelta(days=90)
        txns = []

        configs = {
            "chase_good":  {"pay": 3200, "pay_freq": 14, "pay_jit": 0.02, "rent": 1400, "od": 0, "nsf": 0, "expense_mult": 0.55},
            "wells_avg":   {"pay": 2400, "pay_freq": 14, "pay_jit": 0.05, "rent": 1300, "od": 1, "nsf": 0, "expense_mult": 0.75},
            "bofa_thin":   {"pay": 1800, "pay_freq": 14, "pay_jit": 0.08, "rent": 900,  "od": 0, "nsf": 0, "expense_mult": 0.85},
            "us_bank_gig": {"pay": 600,  "pay_freq": 4,  "pay_jit": 0.40, "rent": 1100, "od": 1, "nsf": 1, "expense_mult": 0.90},
            "chime_risky": {"pay": 1500, "pay_freq": 14, "pay_jit": 0.20, "rent": 1000, "od": 4, "nsf": 2, "expense_mult": 1.05},
        }
        cfg = configs.get(profile, configs["wells_avg"])

        # Paychecks
        d = start
        while d < start + timedelta(days=90):
            amt = cfg["pay"] * (1 + rng.uniform(-cfg["pay_jit"], cfg["pay_jit"]))
            txns.append({"date": d.strftime("%Y-%m-%d"), "amount": round(amt, 2), "category": "payroll"})
            d += timedelta(days=cfg["pay_freq"])

        # Rent monthly
        for m in range(3):
            d = start + timedelta(days=2 + m * 30)
            txns.append({"date": d.strftime("%Y-%m-%d"), "amount": -cfg["rent"], "category": "rent"})

        # Recurring bills
        for cat, amt in [("utilities", -120), ("phone", -75), ("subscription", -15), ("insurance", -150)]:
            for m in range(3):
                d = start + timedelta(days=5 + m * 30 + rng.randint(0, 4))
                txns.append({"date": d.strftime("%Y-%m-%d"), "amount": amt, "category": cat})

        # Variable expenses (groceries, dining, gas)
        n_var = int(60 * cfg["expense_mult"])
        for _ in range(n_var):
            d = start + timedelta(days=rng.randint(0, 89))
            cat = rng.choice(["groceries", "dining", "gas", "shopping"])
            amt = -round(rng.uniform(8, 90), 2)
            txns.append({"date": d.strftime("%Y-%m-%d"), "amount": amt, "category": cat})

        # Overdrafts / NSF
        for _ in range(cfg["od"]):
            d = start + timedelta(days=rng.randint(0, 89))
            txns.append({"date": d.strftime("%Y-%m-%d"), "amount": -34, "category": "overdraft"})
        for _ in range(cfg["nsf"]):
            d = start + timedelta(days=rng.randint(0, 89))
            txns.append({"date": d.strftime("%Y-%m-%d"), "amount": -35, "category": "nsf"})

        return txns
