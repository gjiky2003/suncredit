"""Funding, CECL allowance, and P&L reporting.

CECL (ASC 326) requires recognition of expected credit losses over the life
of the asset at origination. We compute it as

    reserve = Σ_i  outstanding_balance_i  ×  pd_i

where pd_i is the borrower's modeled probability of default. This is a
simplified one-factor implementation suitable for pilot reporting.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

DB_PATH = os.environ.get("SUNCREDIT_DB", os.path.expanduser("~/suncredit/suncredit.db"))


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_tables() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS capital_pools (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_name   TEXT    NOT NULL,
                source      TEXT,
                amount      REAL    NOT NULL,
                rate        REAL,
                opened_at   TEXT    NOT NULL,
                closed_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS loss_reserves (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                as_of_date   TEXT    NOT NULL,
                cecl_reserve REAL    NOT NULL,
                portfolio_balance REAL NOT NULL,
                method       TEXT    DEFAULT 'expected_loss_v1',
                notes        TEXT
            );
            CREATE TABLE IF NOT EXISTS funding_transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_id     INTEGER,
                loan_id     TEXT,
                tx_type     TEXT NOT NULL,   -- deploy | repay | interest | principal | fee | charge_off
                amount      REAL NOT NULL,
                tx_date     TEXT NOT NULL,
                memo        TEXT,
                FOREIGN KEY (pool_id) REFERENCES capital_pools(id)
            );
            CREATE INDEX IF NOT EXISTS idx_ft_date ON funding_transactions(tx_date);
            CREATE INDEX IF NOT EXISTS idx_ft_type ON funding_transactions(tx_type);
            """
        )


def calculate_cecl_reserve(loans: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute expected loss reserve over a portfolio.

    Each loan should provide:
      * loan_balance (or principal_outstanding)
      * default_probability (0..1)
      * loan_id (optional, for breakdown)
    """
    breakdown: List[Dict[str, Any]] = []
    total_balance = 0.0
    total_reserve = 0.0
    for ln in loans:
        bal = float(ln.get("loan_balance", ln.get("principal_outstanding", 0.0)))
        pd = float(ln.get("default_probability", 0.0))
        exp_loss = bal * pd
        total_balance += bal
        total_reserve += exp_loss
        breakdown.append(
            {
                "loan_id": ln.get("loan_id"),
                "loan_balance": round(bal, 2),
                "pd": round(pd, 4),
                "expected_loss": round(exp_loss, 2),
            }
        )
    coverage = (total_reserve / total_balance) if total_balance else 0.0
    return {
        "as_of": datetime.utcnow().isoformat(),
        "portfolio_balance": round(total_balance, 2),
        "cecl_reserve": round(total_reserve, 2),
        "coverage_ratio": round(coverage, 4),
        "method": "expected_loss_v1",
        "loans": breakdown,
    }


def get_funding_summary() -> Dict[str, Any]:
    init_tables()
    with _conn() as c:
        deposited = c.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM capital_pools WHERE closed_at IS NULL"
        ).fetchone()["s"]
        deployed = c.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM funding_transactions WHERE tx_type='deploy'"
        ).fetchone()["s"]
        repaid_principal = c.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM funding_transactions WHERE tx_type='principal'"
        ).fetchone()["s"]
    outstanding = max(0.0, deployed - repaid_principal)
    available = max(0.0, deposited - outstanding)
    return {
        "capital_deposited": round(deposited, 2),
        "capital_deployed": round(deployed, 2),
        "principal_outstanding": round(outstanding, 2),
        "capital_available": round(available, 2),
        "utilization": round(outstanding / deposited, 4) if deposited else 0.0,
    }


def profit_and_loss(start_date: str, end_date: str) -> Dict[str, Any]:
    """Return P&L for a date range. Dates are ISO YYYY-MM-DD."""
    init_tables()
    with _conn() as c:
        def s(t):
            return c.execute(
                "SELECT COALESCE(SUM(amount),0) AS s FROM funding_transactions "
                "WHERE tx_type=? AND tx_date BETWEEN ? AND ?",
                (t, start_date, end_date),
            ).fetchone()["s"]
        interest = s("interest")
        fees = s("fee")
        charge_offs = s("charge_off")
    revenue = interest + fees
    # Pilot opex placeholder; in production sourced from the GL.
    operating_expense = 0.0
    net = revenue - charge_offs - operating_expense
    return {
        "start_date": start_date,
        "end_date": end_date,
        "interest_income": round(interest, 2),
        "fee_income": round(fees, 2),
        "total_revenue": round(revenue, 2),
        "charge_offs": round(charge_offs, 2),
        "operating_expense": round(operating_expense, 2),
        "net_income": round(net, 2),
    }


def get_portfolio_metrics(loans: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """High-level KPIs for the live portfolio."""
    init_tables()
    funding = get_funding_summary()
    n_active = 0
    n_dpd = 0
    weighted_apr = 0.0
    bal = 0.0
    if loans:
        for ln in loans:
            if ln.get("status", "active") == "active":
                n_active += 1
                b = float(ln.get("loan_balance", 0.0))
                bal += b
                weighted_apr += b * float(ln.get("apr", 0.0))
                if int(ln.get("days_past_due", 0)) > 0:
                    n_dpd += 1
        wapr = (weighted_apr / bal) if bal else 0.0
    else:
        wapr = 0.0
    return {
        "active_loans": n_active,
        "delinquent_loans": n_dpd,
        "delinquency_rate": round(n_dpd / n_active, 4) if n_active else 0.0,
        "weighted_avg_apr": round(wapr, 4),
        "principal_outstanding": funding["principal_outstanding"],
        "capital_utilization": funding["utilization"],
    }
