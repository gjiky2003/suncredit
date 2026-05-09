"""Niche underwriting overlays: gig workers, immigrants, medical borrowers."""


class NicheUnderwriter:
    """Niche-specific score/rate adjustments and landing page metadata."""

    NICHES = {
        "gig_worker": {
            "name": "Gig Worker Loans",
            "tagline": "Built for Uber, DoorDash, Instacart & freelance income",
            "credit_boost": 15,
            "cash_flow_weight": 0.55,
            "max_loan": 15000,
            "recommended_product": "Flex Income Personal Loan",
            "interest_adjustment": -0.005,
            "underwriting_signals": [
                "12-week deposit consistency", "platform deposit tagging",
                "expense-to-income ratio under 0.95",
            ],
        },
        "immigrant": {
            "name": "Newcomer Credit Builder",
            "tagline": "No SSN required for thin/no-file borrowers",
            "credit_boost": 25,
            "cash_flow_weight": 0.60,
            "max_loan": 10000,
            "recommended_product": "Newcomer Starter Loan",
            "interest_adjustment": 0.0,
            "underwriting_signals": [
                "ITIN-eligible", "rent payment history", "remittance pattern",
            ],
        },
        "medical": {
            "name": "Medical Bill Financing",
            "tagline": "0% intro APR for verified medical expenses",
            "credit_boost": 10,
            "cash_flow_weight": 0.40,
            "max_loan": 25000,
            "recommended_product": "Medical Hardship Loan",
            "interest_adjustment": -0.02,
            "underwriting_signals": [
                "verified provider invoice", "HSA/insurance EOB", "stable employment",
            ],
        },
    }

    def list_niches(self):
        return [{"id": k, **{kk: vv for kk, vv in v.items() if kk in ("name", "tagline", "max_loan", "recommended_product")}}
                for k, v in self.NICHES.items()]

    def adjust_score_for_niche(self, base_risk_score, niche_id):
        """Lower risk score by credit_boost (clipped to 0)."""
        cfg = self.NICHES.get(niche_id)
        if not cfg:
            return base_risk_score
        return max(0.0, base_risk_score - cfg["credit_boost"])

    def adjust_rate_for_niche(self, base_apr, niche_id):
        cfg = self.NICHES.get(niche_id)
        if not cfg:
            return base_apr
        return max(0.05, base_apr + cfg["interest_adjustment"])

    def get_niche_landing_data(self, niche_id):
        cfg = self.NICHES.get(niche_id)
        if not cfg:
            return None
        return {"id": niche_id, **cfg}

    def get_cash_flow_weight(self, niche_id):
        cfg = self.NICHES.get(niche_id)
        return cfg["cash_flow_weight"] if cfg else None
