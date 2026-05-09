"""Truth in Lending Act (TILA / Regulation Z) disclosure generator.

Produces the federally-required TILA disclosure box for closed-end consumer
installment loans. Output is offered both as a structured dict (for storage
and downstream rendering) and as a self-contained HTML fragment suitable for
embedding in the loan agreement PDF / e-sign flow.
"""
from __future__ import annotations

from typing import Any, Dict


def _payment_schedule(loan: Dict[str, Any]) -> Dict[str, Any]:
    n = int(loan.get("term_months", 0))
    monthly = float(loan.get("monthly_payment", 0.0))
    return {
        "number_of_payments": n,
        "payment_amount": round(monthly, 2),
        "total_of_payments": round(monthly * n, 2),
        "frequency": "monthly",
    }


def generate_tila_disclosure(loan: Dict[str, Any]) -> Dict[str, Any]:
    """Return the TILA disclosure for a loan record.

    Expected loan keys: principal, apr, term_months, monthly_payment,
    finance_charge (optional), late_fee (optional).
    """
    principal = float(loan.get("principal", 0.0))
    apr = float(loan.get("apr", 0.0))
    sched = _payment_schedule(loan)
    total = sched["total_of_payments"]
    finance_charge = float(loan.get("finance_charge", round(total - principal, 2)))
    late_fee = float(loan.get("late_fee", 25.00))

    disclosure = {
        "amount_financed": round(principal, 2),
        "finance_charge": round(finance_charge, 2),
        "total_of_payments": round(total, 2),
        "apr": round(apr, 4),
        "payment_schedule_summary": sched,
        "prepayment_penalty": False,
        "prepayment_penalty_text": "You will not be charged a penalty if you pay off early.",
        "late_fee": late_fee,
        "late_fee_text": f"If a payment is more than 10 days late, you will be charged ${late_fee:.2f}.",
        "security_interest": "None. This is an unsecured consumer installment loan.",
        "required_deposit": False,
    }
    disclosure["html"] = render_tila_html(disclosure)
    return disclosure


def render_tila_html(d: Dict[str, Any]) -> str:
    sched = d["payment_schedule_summary"]
    return f"""
<table class="tila-box" style="border:2px solid #000;border-collapse:collapse;font-family:Arial,sans-serif;width:100%;max-width:720px;">
  <thead>
    <tr style="background:#f1f5f9;">
      <th style="border:1px solid #000;padding:8px;">ANNUAL PERCENTAGE RATE</th>
      <th style="border:1px solid #000;padding:8px;">FINANCE CHARGE</th>
      <th style="border:1px solid #000;padding:8px;">Amount Financed</th>
      <th style="border:1px solid #000;padding:8px;">Total of Payments</th>
    </tr>
    <tr style="font-size:11px;color:#475569;">
      <td style="border:1px solid #000;padding:6px;">The cost of your credit as a yearly rate.</td>
      <td style="border:1px solid #000;padding:6px;">The dollar amount the credit will cost you.</td>
      <td style="border:1px solid #000;padding:6px;">The amount of credit provided to you or on your behalf.</td>
      <td style="border:1px solid #000;padding:6px;">The amount you will have paid after all scheduled payments.</td>
    </tr>
  </thead>
  <tbody>
    <tr style="font-size:18px;font-weight:bold;text-align:center;">
      <td style="border:1px solid #000;padding:10px;">{d['apr']*100:.2f}%</td>
      <td style="border:1px solid #000;padding:10px;">${d['finance_charge']:.2f}</td>
      <td style="border:1px solid #000;padding:10px;">${d['amount_financed']:.2f}</td>
      <td style="border:1px solid #000;padding:10px;">${d['total_of_payments']:.2f}</td>
    </tr>
  </tbody>
  <tfoot>
    <tr><td colspan="4" style="border:1px solid #000;padding:8px;font-size:12px;">
      <b>Payment Schedule:</b> {sched['number_of_payments']} monthly payments of
      ${sched['payment_amount']:.2f} totaling ${sched['total_of_payments']:.2f}.<br>
      <b>Prepayment:</b> {d['prepayment_penalty_text']}<br>
      <b>Late Charge:</b> {d['late_fee_text']}<br>
      <b>Security:</b> {d['security_interest']}<br>
      <b>Required Deposit:</b> The annual percentage rate does not take into account any required deposit.
    </td></tr>
  </tfoot>
</table>
""".strip()
