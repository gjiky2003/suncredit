"""Risk-based pricing engine for SunCredit loans.

Maps risk score (0-100, higher=riskier) → APR tier, monthly payment, origination fee.
"""


class PricingEngine:
    """Risk-tier pricing with amortized monthly payment calc."""

    # tier: (low_score, high_score, low_apr, high_apr, orig_fee_pct)
    TIERS = [
        ("A", 0,  20, 0.10, 0.13, 0.01),
        ("B", 20, 40, 0.13, 0.17, 0.02),
        ("C", 40, 60, 0.17, 0.22, 0.03),
        ("D", 60, 80, 0.22, 0.26, 0.04),
        ("E", 80, 101,0.26, 0.29, 0.05),
    ]

    def get_tier(self, risk_score):
        for tier in self.TIERS:
            label, lo, hi, _, _, _ = tier
            if lo <= risk_score < hi:
                return tier
        return self.TIERS[-1]

    def price_loan(self, risk_score, amount, term):
        tier = self.get_tier(risk_score)
        label, lo, hi, lo_apr, hi_apr, orig_pct = tier
        # interpolate APR within tier
        frac = (risk_score - lo) / max(hi - lo, 1)
        frac = max(0.0, min(1.0, frac))
        apr = lo_apr + frac * (hi_apr - lo_apr)

        r = apr / 12.0
        n = max(int(term), 1)
        if r > 0:
            monthly = amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
        else:
            monthly = amount / n
        origination_fee = round(amount * orig_pct, 2)

        return {
            "interest_rate": round(apr, 4),
            "monthly_payment": round(monthly, 2),
            "origination_fee": origination_fee,
            "tier": label,
            "term_months": n,
            "total_interest": round(monthly * n - amount, 2),
        }
