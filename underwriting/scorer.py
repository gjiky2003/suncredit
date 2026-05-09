"""Top-level loan scorer: orchestrates ML + cash flow, returns decision."""
import os
import json
import numpy as np

from underwriting.feature_engineer import FeatureEngineer
from underwriting.ensemble_model import EnsembleModel
from underwriting.pricing import PricingEngine

HERE = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_PATH = os.path.join(HERE, "model_weights.json")


class LoanScorer:
    """Main entrypoint for application scoring. Auto-loads model_weights.json."""

    def __init__(self, weights_path=WEIGHTS_PATH):
        self.fe = FeatureEngineer()
        self.model = EnsembleModel()
        self.pricing = PricingEngine()
        self.loaded = False
        self.feature_importance = {}
        if os.path.exists(weights_path):
            with open(weights_path) as f:
                d = json.load(f)
            self.fe.from_dict(d["feature_engineer"])
            self.model.from_dict(d["ensemble"])
            self.feature_importance = d.get("feature_importance", {})
            self.loaded = True

    def _ml_risk(self, app_data):
        """Return risk 0-100. Falls back to rule-based if model not loaded."""
        if self.loaded:
            X = self.fe.transform([app_data])
            p = float(self.model.predict_proba(X)[0])
            return max(0.0, min(100.0, p * 100.0))
        # fallback heuristic
        cs = float(app_data.get("credit_score", 650))
        dti = float(app_data.get("dti_ratio", 0.3))
        derog = float(app_data.get("num_derogatory", 0))
        risk = (720 - cs) * 0.25 + dti * 80 + derog * 6 + 25
        return max(0.0, min(100.0, risk))

    def _cf_weight(self, app_data, cf):
        cs = float(app_data.get("credit_score", 700))
        cf_score = float(cf.get("cash_flow_score", 50))
        if cf_score < 30:
            return 0.60
        if cs < 620:
            return 0.50
        return 0.30

    def _tier(self, risk):
        if risk < 20: return "A"
        if risk < 40: return "B"
        if risk < 60: return "C"
        if risk < 80: return "D"
        return "E"

    def _reasons(self, app, cf, ml_risk, cf_weight, final_risk):
        r = []
        cs = float(app.get("credit_score", 0))
        if cs >= 720: r.append(f"Strong credit score ({int(cs)}) supports approval")
        elif cs >= 660: r.append(f"Acceptable credit score ({int(cs)})")
        else: r.append(f"Subprime credit score ({int(cs)}) elevates risk")

        dti = float(app.get("dti_ratio", 0))
        if dti < 0.2: r.append(f"Low DTI ratio ({dti:.0%}) indicates capacity")
        elif dti < 0.4: r.append(f"Moderate DTI ratio ({dti:.0%})")
        else: r.append(f"High DTI ratio ({dti:.0%}) constrains capacity")

        derog = int(app.get("num_derogatory", 0))
        if derog == 0: r.append("Clean credit history (no derogatory marks)")
        else: r.append(f"{derog} derogatory mark(s) on credit file")

        if cf:
            cfs = cf.get("cash_flow_score", 0)
            r.append(f"Cash flow score {cfs:.0f}/100 weighted at {int(cf_weight*100)}%")
            if cf.get("overdraft_count", 0) > 2:
                r.append(f"Frequent overdrafts ({cf['overdraft_count']}) — caution flag")
            if cf.get("paycheck_regularity", 0) >= 80:
                r.append("Highly regular paycheck pattern")

        r.append(f"ML risk {ml_risk:.0f} → final risk {final_risk:.0f}")
        return r

    def score_application(self, app_data, cash_flow_data=None):
        ml_risk = self._ml_risk(app_data)
        if cash_flow_data:
            w = self._cf_weight(app_data, cash_flow_data)
            cf_risk = 100.0 - float(cash_flow_data.get("cash_flow_score", 50))
            final_risk = ml_risk * (1.0 - w) + cf_risk * w
        else:
            w = 0.0
            final_risk = ml_risk

        final_risk = max(0.0, min(100.0, final_risk))
        tier = self._tier(final_risk)

        amount = float(app_data.get("loan_amount", 5000))
        term = int(app_data.get("term_months", app_data.get("term", 36)))
        pricing = self.pricing.price_loan(final_risk, amount, term)

        approved = final_risk < 80 and float(app_data.get("credit_score", 0)) >= 540

        return {
            "risk_score": round(final_risk, 1),
            "risk_tier": tier,
            "interest_rate": pricing["interest_rate"],
            "monthly_payment": pricing["monthly_payment"],
            "origination_fee": pricing["origination_fee"],
            "approved": bool(approved),
            "decision_reasons": self._reasons(app_data, cash_flow_data, ml_risk, w, final_risk),
            "cash_flow_weight": round(w, 2),
            "ml_risk": round(ml_risk, 1),
            "term_months": term,
        }
