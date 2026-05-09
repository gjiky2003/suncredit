"""Identity verification helpers: OFAC / PEP screening + KBA.

Production should call OFAC SDN list (Treasury), Dow Jones / Refinitiv PEP
data, and a KBA vendor (LexisNexis, Experian Precise ID). This module
provides functional placeholders so the lending pipeline can run end-to-end
in dev/pilot mode.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

# Placeholder OFAC SDN entries (real list at
# https://www.treasury.gov/ofac/downloads/sdn.csv)
_SANCTIONED: List[Dict[str, str]] = [
    {"name": "Vladimir Putin", "dob": "1952-10-07"},
    {"name": "Kim Jong Un", "dob": "1984-01-08"},
    {"name": "Bashar al-Assad", "dob": "1965-09-11"},
    {"name": "Specially Designated Test Person", "dob": "1970-01-01"},
]

_PEPS: List[str] = [
    "Joe Biden", "Donald Trump", "Barack Obama",
    "Greg Abbott", "Janet Yellen", "Jerome Powell",
]


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def ofac_check(name: str, dob: Optional[str] = None) -> Dict[str, Any]:
    """Return match info against placeholder OFAC list."""
    n = _normalize(name)
    matches = [
        s for s in _SANCTIONED
        if _normalize(s["name"]) == n and (dob is None or s["dob"] == dob)
    ]
    return {
        "name": name,
        "dob": dob,
        "match": bool(matches),
        "matches": matches,
        "list": "OFAC SDN (placeholder)",
        "action": "DECLINE — sanctioned individual" if matches else "PASS",
    }


def pep_check(name: str) -> Dict[str, Any]:
    n = _normalize(name)
    is_pep = any(_normalize(p) == n for p in _PEPS)
    return {
        "name": name,
        "is_pep": is_pep,
        "list": "PEP screening (placeholder)",
        "action": "ENHANCED_DUE_DILIGENCE" if is_pep else "PASS",
    }


def knowledge_based_auth_questions(borrower_id: str) -> List[Dict[str, Any]]:
    """Return 3 knowledge-based authentication questions.

    Real implementation pulls from the borrower's bureau file and generates
    out-of-wallet questions (former addresses, lender names, vehicle make).
    Here we generate plausible-looking fixtures seeded by borrower_id so
    repeat calls are stable for the same borrower.
    """
    rng = random.Random(borrower_id)
    bank_pool = ["Chase", "Wells Fargo", "Bank of America", "Capital One", "Citi", "USAA"]
    car_pool = ["Toyota", "Honda", "Ford", "Chevrolet", "Nissan", "Hyundai"]
    street_pool = ["Maple", "Oak", "Elm", "Pine", "Cedar", "Walnut"]

    return [
        {
            "id": "kba_1",
            "question": "Which of the following lenders have you held an auto loan with in the last 7 years?",
            "options": rng.sample(bank_pool, 4) + ["None of the above"],
        },
        {
            "id": "kba_2",
            "question": "Which of the following vehicle makes have you been associated with?",
            "options": rng.sample(car_pool, 4) + ["None of the above"],
        },
        {
            "id": "kba_3",
            "question": "Which of the following street names have you lived on?",
            "options": [f"{s} St" for s in rng.sample(street_pool, 4)] + ["None of the above"],
        },
    ]
