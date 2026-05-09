"""Loan collections workflow. Stages 0-5 by days past due."""
import os
import sys
import json
import sqlite3
from datetime import datetime, date


def _get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'platform', 'suncredit.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


STAGE_BANDS = [
    (0, 0, 10),
    (1, 11, 30),
    (2, 31, 60),
    (3, 61, 90),
    (4, 91, 120),
    (5, 121, 10**9),
]

STAGE_ACTIONS = {
    0: 'gentle_reminder',
    1: 'overdue_notice',
    2: 'urgent_late_fee',
    3: 'final_notice',
    4: 'legal_referral',
    5: 'charge_off',
}

LATE_FEE_CENTS = 2500  # $25 at stage 2


def _stage_for(days):
    for s, lo, hi in STAGE_BANDS:
        if lo <= days <= hi:
            return s
    return 5


def _days_past_due(due_date_str, today=None):
    if not due_date_str:
        return 0
    today = today or date.today()
    try:
        due = datetime.fromisoformat(str(due_date_str)[:10]).date()
    except Exception:
        return 0
    delta = (today - due).days
    return max(0, delta)


def _overdue_loans(conn):
    """Return loans with at least one overdue scheduled payment."""
    today = date.today().isoformat()
    rows = conn.execute(
        """
        SELECT l.*,
               (SELECT MIN(ps.due_date) FROM payment_schedules ps
                  WHERE ps.loan_id=l.id AND ps.status!='paid' AND ps.due_date < ?) AS oldest_unpaid_due
          FROM loans l
         WHERE l.status IN ('active','delinquent','past_due')
        """,
        (today,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get('oldest_unpaid_due'):
            d['days_past_due'] = _days_past_due(d['oldest_unpaid_due'])
            if d['days_past_due'] > 0:
                out.append(d)
        elif (r['next_payment_date']):
            dpd = _days_past_due(r['next_payment_date'])
            if dpd > 0:
                d['days_past_due'] = dpd
                out.append(d)
    return out


def get_collection_stats():
    conn = _get_db()
    overdue = _overdue_loans(conn)
    stage_counts = {i: 0 for i in range(6)}
    total_at_risk = 0.0
    for l in overdue:
        s = _stage_for(l['days_past_due'])
        stage_counts[s] += 1
        total_at_risk += l.get('remaining_balance', 0) or 0

    charged_off_row = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(remaining_balance),0) s FROM loans WHERE status='charged_off'"
    ).fetchone()
    conn.close()

    return {
        'total_overdue': len(overdue),
        'stage_counts': stage_counts,
        'total_at_risk': round(total_at_risk, 2),
        'total_charged_off_count': charged_off_row['c'],
        'total_charged_off': round(charged_off_row['s'] or 0, 2),
        'computed_at': datetime.utcnow().isoformat(),
    }


def _send_notice(borrower_id, loan_id, dpd, stage):
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        import notifications
        notifications.send_collection_notice(borrower_id, loan_id, dpd, stage)
        return True
    except Exception as e:
        print(f"[collections] notify failed: {e}")
        return False


def process_loan(loan_id):
    conn = _get_db()
    loan = conn.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
    if not loan:
        conn.close()
        return {'ok': False, 'error': 'loan_not_found'}

    # Find earliest unpaid scheduled due date
    today = date.today().isoformat()
    sched = conn.execute(
        "SELECT MIN(due_date) d FROM payment_schedules WHERE loan_id=? AND status!='paid' AND due_date < ?",
        (loan_id, today),
    ).fetchone()
    oldest = sched['d'] if sched else None
    if not oldest:
        oldest = loan['next_payment_date']
    dpd = _days_past_due(oldest) if oldest else 0
    if dpd <= 0:
        conn.close()
        return {'ok': True, 'loan_id': loan_id, 'days_past_due': 0, 'action': 'none', 'stage': None}

    stage = _stage_for(dpd)
    action = STAGE_ACTIONS[stage]

    # Find prior collection stage
    prior = conn.execute(
        "SELECT MAX(collection_stage) m FROM collections WHERE loan_id=?",
        (loan_id,),
    ).fetchone()
    prior_stage = prior['m'] if prior and prior['m'] is not None else -1

    notice_sent = False
    if stage > prior_stage:
        notice_sent = _send_notice(loan['borrower_id'], loan_id, dpd, stage)

    # Stage 2: assess late fee once
    if stage >= 2:
        existing_fee = conn.execute(
            "SELECT id FROM payments WHERE loan_id=? AND payment_type='late_fee'",
            (loan_id,),
        ).fetchone()
        if not existing_fee:
            conn.execute(
                "INSERT INTO payments (loan_id, borrower_id, amount_cents, payment_type, status) VALUES (?,?,?,?,?)",
                (loan_id, loan['borrower_id'], LATE_FEE_CENTS, 'late_fee', 'pending'),
            )

    # Stage 5: charge off
    new_loan_status = loan['status']
    if stage == 5 and loan['status'] != 'charged_off':
        new_loan_status = 'charged_off'
        conn.execute("UPDATE loans SET status='charged_off' WHERE id=?", (loan_id,))
    elif stage >= 1 and loan['status'] == 'active':
        new_loan_status = 'delinquent'
        conn.execute("UPDATE loans SET status='delinquent' WHERE id=?", (loan_id,))

    # Record collections action
    conn.execute(
        "INSERT INTO collections (loan_id, borrower_id, collection_stage, days_past_due, action_taken, communication_channel) "
        "VALUES (?,?,?,?,?,?)",
        (loan_id, loan['borrower_id'], stage, dpd, action, 'email'),
    )
    conn.execute(
        "INSERT INTO audit_logs (action_type, borrower_id, actor, details) VALUES (?,?,?,?)",
        ('collections_action', loan['borrower_id'], 'system',
         json.dumps({'loan_id': loan_id, 'stage': stage, 'dpd': dpd, 'action': action})),
    )
    conn.commit()
    conn.close()

    return {
        'ok': True,
        'loan_id': loan_id,
        'borrower_id': loan['borrower_id'],
        'days_past_due': dpd,
        'stage': stage,
        'action': action,
        'prior_stage': prior_stage,
        'notice_sent': notice_sent,
        'loan_status': new_loan_status,
    }


def run_collections_cycle():
    conn = _get_db()
    overdue = _overdue_loans(conn)
    conn.close()

    results = []
    for l in overdue:
        try:
            results.append(process_loan(l['id']))
        except Exception as e:
            results.append({'ok': False, 'loan_id': l['id'], 'error': str(e)})

    summary = {
        'cycle_at': datetime.utcnow().isoformat(),
        'processed': len(results),
        'results': results,
        'stats': get_collection_stats(),
    }
    return summary


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'stats':
        print(json.dumps(get_collection_stats(), indent=2))
    else:
        print(json.dumps(run_collections_cycle(), indent=2, default=str))
