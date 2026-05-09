"""State-by-state usury caps and consumer-lender licensing rules.

Values are PILOT-PHASE GUIDANCE only. Each state's actual statute, license
type, and bond schedule must be re-verified with state counsel before
originating in that jurisdiction. URLs point to the principal regulator.
"""
from __future__ import annotations

from typing import Any, Dict


# max_apr is expressed as a decimal (0.36 = 36% APR). None means "no
# specific small-loan cap; subject to general usury or bank-rate exportation."
STATE_RULES: Dict[str, Dict[str, Any]] = {
    "AL": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://banking.alabama.gov/"},
    "AK": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.commerce.alaska.gov/web/dbs/"},
    "AZ": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dfi.az.gov/"},
    "AR": {"max_apr": 0.17, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  50000, "regulator_url": "https://securities.arkansas.gov/"},
    "CA": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dfpi.ca.gov/"},
    "CO": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://coag.gov/office-sections/consumer-protection/consumer-credit-unit/"},
    "CT": {"max_apr": 0.12, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  40000, "regulator_url": "https://portal.ct.gov/dob"},
    "DE": {"max_apr": None, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://banking.delaware.gov/"},
    "FL": {"max_apr": 0.30, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://flofr.gov/"},
    "GA": {"max_apr": 0.60, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dbf.georgia.gov/"},
    "HI": {"max_apr": 0.24, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://cca.hawaii.gov/dfi/"},
    "ID": {"max_apr": None, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dof.idaho.gov/"},
    "IL": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://idfpr.illinois.gov/"},
    "IN": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.in.gov/dfi/"},
    "IA": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://idob.state.ia.us/"},
    "KS": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://osbckansas.org/"},
    "KY": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://kfi.ky.gov/"},
    "LA": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.ofi.la.gov/"},
    "ME": {"max_apr": 0.30, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.maine.gov/pfr/financialinstitutions/"},
    "MD": {"max_apr": 0.33, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.dllr.state.md.us/finance/"},
    "MA": {"max_apr": 0.23, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  75000, "regulator_url": "https://www.mass.gov/orgs/division-of-banks"},
    "MI": {"max_apr": 0.25, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.michigan.gov/difs"},
    "MN": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  50000, "regulator_url": "https://mn.gov/commerce/"},
    "MS": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dbcf.ms.gov/"},
    "MO": {"max_apr": None, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://finance.mo.gov/"},
    "MT": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://banking.mt.gov/"},
    "NE": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://ndbf.nebraska.gov/"},
    "NV": {"max_apr": 0.40, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  50000, "regulator_url": "https://fid.nv.gov/"},
    "NH": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.nh.gov/banking/"},
    "NJ": {"max_apr": 0.30, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.state.nj.us/dobi/"},
    "NM": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.rld.nm.gov/financial-institutions/"},
    "NY": {"max_apr": 0.16, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  50000, "regulator_url": "https://www.dfs.ny.gov/"},
    "NC": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.nccob.gov/"},
    "ND": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.nd.gov/dfi/"},
    "OH": {"max_apr": 0.28, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://com.ohio.gov/divisions-and-programs/financial-institutions/"},
    "OK": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.ok.gov/okdocc/"},
    "OR": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dfr.oregon.gov/"},
    "PA": {"max_apr": 0.24, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.dobs.pa.gov/"},
    "RI": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dbr.ri.gov/"},
    "SC": {"max_apr": None, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://consumer.sc.gov/"},
    "SD": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dlr.sd.gov/banking/"},
    "TN": {"max_apr": 0.24, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.tn.gov/tdfi/"},
    "TX": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://occc.texas.gov/"},
    "UT": {"max_apr": None, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dfi.utah.gov/"},
    "VT": {"max_apr": 0.18, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  50000, "regulator_url": "https://dfr.vermont.gov/"},
    "VA": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://www.scc.virginia.gov/pages/Bureau-of-Financial-Institutions"},
    "WA": {"max_apr": 0.25, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  30000, "regulator_url": "https://dfi.wa.gov/"},
    "WV": {"max_apr": 0.31, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dfi.wv.gov/"},
    "WI": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://dfi.wi.gov/"},
    "WY": {"max_apr": 0.36, "license_required": True,  "registered_agent_required": True, "surety_bond_amount":  25000, "regulator_url": "https://wyomingbankingdivision.wyo.gov/"},
}


def is_legal_state(state: str, apr: float, loan_amount: float) -> Dict[str, Any]:
    s = (state or "").upper()
    rule = STATE_RULES.get(s)
    if not rule:
        return {"legal": False, "reason": f"Unknown state '{state}'"}
    reasons = []
    cap = rule.get("max_apr")
    if cap is not None and apr > cap:
        reasons.append(f"APR {apr*100:.2f}% exceeds {s} cap of {cap*100:.2f}%")
    if loan_amount <= 0:
        reasons.append("Loan amount must be positive")
    return {
        "legal": not reasons,
        "state": s,
        "rule": rule,
        "reasons": reasons,
    }
