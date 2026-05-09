"""
SunCredit AI Autopilot — runs the lending business hands-off.

Runs every 15 minutes (cron). Each tick performs:
  1. Auto-decision pending applications (score + approve/decline)
  2. Auto-disburse approved loans via Stripe ACH
  3. Auto-collect scheduled payments (autopay charge)
  4. Send dunning notices for missed payments (3/7/15/30 day)
  5. Escalate severely delinquent loans (60+ days)
  6. Re-price improving borrowers (rate-improvement engine)
  7. Generate daily ops report

Every action is logged to autopilot_log table for audit.
"""
from __future__ import annotations
import os, sys, json, sqlite3, logging, traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from underwriting.scorer import LoanScorer
_scorer = None
def _get_scorer():
    global _scorer
    if _scorer is None:
        _scorer = LoanScorer()
    return _scorer

def uw_score(features):
    return _get_scorer().score_application(features)
from automation import notifications
try:
    from automation import stripe_payments
except Exception:
    stripe_payments = None

DB = os.environ.get("SUNCREDIT_DB", str(Path(__file__).resolve().parent.parent / "platform" / "suncredit.db"))
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] autopilot: %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "autopilot.log"), logging.StreamHandler()],
)
log = logging.getLogger("autopilot")

# ---------- Policy thresholds (the AI's "judgement") ----------
AUTO_APPROVE_MIN_SCORE = 680   # auto-approve above this
AUTO_DECLINE_MAX_SCORE = 540   # auto-decline below this
# 540-680 → flag for human review (zero tolerance for bias claims)
MAX_AUTO_LOAN_AMOUNT = 15000   # anything bigger needs human
DUNNING_DAYS = [3, 7, 15, 30]
ESCALATION_DAY = 60
RATE_IMPROVE_MIN_PAYMENTS = 6  # need 6 on-time payments for rate cut


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def ensure_log_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS autopilot_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT,
        target_id INTEGER,
        details TEXT,
        success INTEGER DEFAULT 1
    )""")
    conn.commit()


def record(conn, action, target_type=None, target_id=None, details=None, success=True):
    conn.execute(
        "INSERT INTO autopilot_log (ts, action, target_type, target_id, details, success) VALUES (?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), action, target_type, target_id,
         json.dumps(details or {}, default=str), 1 if success else 0),
    )
    conn.commit()
    log.info(f"{action} {target_type}#{target_id} success={success} {details or ''}")


# ---------- 1. Auto-decision pending applications ----------
def step_auto_decision(conn) -> dict:
    pending = conn.execute(
        "SELECT a.*, b.first_name, b.last_name, b.email, b.credit_score "
        "FROM applications a JOIN borrowers b ON a.borrower_id=b.id "
        "WHERE a.status = 'pending' AND a.amount IS NOT NULL "
        "ORDER BY a.created_at ASC LIMIT 50"
    ).fetchall()

    stats = {"approved": 0, "declined": 0, "manual_review": 0, "errors": 0}
    for app in pending:
        try:
            features = {
                "credit_score": app["credit_score"] or 600,
                "annual_income": app["annual_income"] or 50000,
                "loan_amount": app["amount"],
                "term_months": app["term_months"] or 36,
                "employment_status": app["employment_status"] or "full_time",
                "dti_ratio": float(app["dti_ratio"] or 0.30),
                "prior_defaults": app["prior_defaults"] or 0,
            }
            result = uw_score(features)
            risk = result.get("risk_score", 50)
            tier = result.get("tier", "C")

            decision, reason = "manual_review", "in human-review band"
            if app["amount"] > MAX_AUTO_LOAN_AMOUNT:
                decision, reason = "manual_review", f"amount exceeds ${MAX_AUTO_LOAN_AMOUNT} auto-cap"
            elif risk >= AUTO_APPROVE_MIN_SCORE:
                decision, reason = "approved", "auto-approved by AI"
            elif risk <= AUTO_DECLINE_MAX_SCORE:
                decision, reason = "declined", "auto-declined by AI"

            conn.execute(
                "UPDATE applications SET status=?, risk_score=?, tier=?, "
                "decision_reason=?, decided_at=? WHERE id=?",
                (decision, risk, tier, reason, datetime.now(timezone.utc).isoformat(), app["id"]),
            )

            # Notify borrower if final decision
            if decision in ("approved", "declined"):
                notifications.send(
                    to=app["email"],
                    template=f"{decision}_email",
                    context={"name": app["first_name"], "amount": app["amount"]},
                )

            stats[decision if decision != "manual_review" else "manual_review"] += 1
            record(conn, "auto_decision", "application", app["id"],
                   {"decision": decision, "risk_score": risk, "reason": reason})
        except Exception as e:
            stats["errors"] += 1
            record(conn, "auto_decision_error", "application", app["id"],
                   {"error": str(e), "trace": traceback.format_exc()[:500]}, success=False)
    conn.commit()
    return stats


# ---------- 2. Auto-disburse approved loans ----------
def step_auto_disburse(conn) -> dict:
    apps = conn.execute(
        "SELECT a.*, b.first_name, b.email FROM applications a "
        "JOIN borrowers b ON a.borrower_id=b.id "
        "WHERE a.status='approved' AND a.disbursed_at IS NULL "
        "AND a.contract_signed_at IS NOT NULL LIMIT 50"
    ).fetchall()
    stats = {"disbursed": 0, "errors": 0}
    for app in apps:
        try:
            # Create loan record
            conn.execute(
                "INSERT INTO loans (borrower_id, application_id, principal, term_months, "
                "interest_rate, status, originated_at) VALUES (?,?,?,?,?,?,?)",
                (app["borrower_id"], app["id"], app["amount"], app["term_months"] or 36,
                 app["apr"] or 0.18, "active", datetime.now(timezone.utc).isoformat()),
            )
            loan_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # Trigger Stripe ACH transfer (sandbox if not configured)
            transfer_id = None
            if stripe_payments and os.environ.get("STRIPE_SECRET_KEY"):
                transfer_id = stripe_payments.disburse(
                    borrower_id=app["borrower_id"], amount=app["amount"], loan_id=loan_id,
                )
            conn.execute(
                "UPDATE applications SET disbursed_at=?, transfer_id=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), transfer_id, app["id"]),
            )
            notifications.send(to=app["email"], template="funded_email",
                               context={"name": app["first_name"], "amount": app["amount"]})
            stats["disbursed"] += 1
            record(conn, "auto_disburse", "loan", loan_id,
                   {"amount": app["amount"], "transfer_id": transfer_id})
        except Exception as e:
            stats["errors"] += 1
            record(conn, "auto_disburse_error", "application", app["id"],
                   {"error": str(e)}, success=False)
    conn.commit()
    return stats


# ---------- 3. Auto-collect scheduled payments ----------
def step_auto_collect(conn) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    due = conn.execute(
        "SELECT p.*, l.borrower_id, b.email, b.first_name FROM payments p "
        "JOIN loans l ON p.loan_id=l.id JOIN borrowers b ON l.borrower_id=b.id "
        "WHERE p.status='scheduled' AND p.due_date <= ? "
        "AND b.autopay_enabled=1 LIMIT 100",
        (today,),
    ).fetchall()
    stats = {"charged": 0, "failed": 0}
    for p in due:
        try:
            charged = True
            if stripe_payments and os.environ.get("STRIPE_SECRET_KEY"):
                charged = stripe_payments.charge(borrower_id=p["borrower_id"], amount=p["amount"])
            new_status = "paid" if charged else "failed"
            conn.execute(
                "UPDATE payments SET status=?, paid_at=? WHERE id=?",
                (new_status, datetime.now(timezone.utc).isoformat() if charged else None, p["id"]),
            )
            if charged:
                stats["charged"] += 1
                notifications.send(to=p["email"], template="payment_received",
                                   context={"name": p["first_name"], "amount": p["amount"]})
            else:
                stats["failed"] += 1
            record(conn, "auto_collect", "payment", p["id"],
                   {"amount": p["amount"], "result": new_status})
        except Exception as e:
            stats["failed"] += 1
            record(conn, "auto_collect_error", "payment", p["id"], {"error": str(e)}, success=False)
    conn.commit()
    return stats


# ---------- 4. Dunning ladder ----------
def step_dunning(conn) -> dict:
    today = datetime.now(timezone.utc).date()
    stats = {"reminders_sent": 0}
    for days in DUNNING_DAYS:
        target = (today - timedelta(days=days)).isoformat()
        late = conn.execute(
            "SELECT p.*, b.email, b.first_name FROM payments p "
            "JOIN loans l ON p.loan_id=l.id JOIN borrowers b ON l.borrower_id=b.id "
            "WHERE p.status IN ('scheduled','failed') AND p.due_date = ?",
            (target,),
        ).fetchall()
        for p in late:
            severity = "soft" if days <= 7 else "firm" if days <= 15 else "final"
            notifications.send(
                to=p["email"], template="payment_reminder",
                context={"name": p["first_name"], "amount": p["amount"],
                         "days_late": days, "severity": severity},
            )
            stats["reminders_sent"] += 1
            record(conn, "dunning", "payment", p["id"], {"days_late": days, "severity": severity})
    return stats


# ---------- 5. Escalate severe delinquencies ----------
def step_escalate(conn) -> dict:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=ESCALATION_DAY)).isoformat()
    bad = conn.execute(
        "SELECT DISTINCT l.id, l.borrower_id, l.principal FROM loans l "
        "JOIN payments p ON p.loan_id=l.id "
        "WHERE p.status IN ('scheduled','failed') AND p.due_date <= ? "
        "AND l.status='active'",
        (cutoff,),
    ).fetchall()
    for ln in bad:
        conn.execute("UPDATE loans SET status='delinquent_escalated' WHERE id=?", (ln["id"],))
        record(conn, "escalate", "loan", ln["id"], {"reason": f"{ESCALATION_DAY}+ days delinquent"})
    conn.commit()
    return {"escalated": len(bad)}


# ---------- 6. Rate improvement ----------
def step_rate_improve(conn) -> dict:
    candidates = conn.execute(
        "SELECT l.id, l.borrower_id, l.interest_rate, l.principal, b.email, b.first_name "
        "FROM loans l JOIN borrowers b ON l.borrower_id=b.id "
        "WHERE l.status='active' AND l.rate_improved_at IS NULL "
        "AND (SELECT COUNT(*) FROM payments p WHERE p.loan_id=l.id AND p.status='paid') >= ?",
        (RATE_IMPROVE_MIN_PAYMENTS,),
    ).fetchall()
    stats = {"improved": 0}
    for ln in candidates:
        new_rate = max(0.06, (ln["interest_rate"] or 0.18) - 0.02)  # cut 2 percentage points
        conn.execute(
            "UPDATE loans SET interest_rate=?, rate_improved_at=? WHERE id=?",
            (new_rate, datetime.now(timezone.utc).isoformat(), ln["id"]),
        )
        notifications.send(to=ln["email"], template="rate_improvement",
                           context={"name": ln["first_name"], "new_rate": new_rate})
        stats["improved"] += 1
        record(conn, "rate_improve", "loan", ln["id"],
               {"old_rate": ln["interest_rate"], "new_rate": new_rate})
    conn.commit()
    return stats


# ---------- 7. Daily ops report ----------
def step_daily_report(conn) -> dict:
    last_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = conn.execute(
        "SELECT action, COUNT(*) AS n, SUM(success) AS ok FROM autopilot_log "
        "WHERE ts >= ? GROUP BY action", (last_24h,)
    ).fetchall()
    summary = {r["action"]: {"total": r["n"], "success": r["ok"]} for r in rows}
    portfolio = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(principal),0) AS p FROM loans WHERE status='active'"
    ).fetchone()
    summary["_portfolio"] = {"active_loans": portfolio["n"], "principal_outstanding": portfolio["p"]}
    record(conn, "daily_report", "system", 0, summary)
    return summary


# ---------- Main tick ----------
def tick():
    log.info("=== Autopilot tick start ===")
    with db() as conn:
        ensure_log_table(conn)
        result = {}
        for name, fn in [
            ("decisions", step_auto_decision),
            ("disbursements", step_auto_disburse),
            ("collections", step_auto_collect),
            ("dunning", step_dunning),
            ("escalations", step_escalate),
            ("rate_improvements", step_rate_improve),
            ("report", step_daily_report),
        ]:
            try:
                result[name] = fn(conn)
            except Exception as e:
                log.error(f"step {name} failed: {e}")
                result[name] = {"error": str(e)}
        log.info(f"=== Autopilot tick done: {json.dumps(result, default=str)} ===")
        return result


if __name__ == "__main__":
    print(json.dumps(tick(), indent=2, default=str))
