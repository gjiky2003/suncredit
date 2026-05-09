"""Stripe payment automation. Mock-friendly: returns 'real': False when keys missing."""
import os
import json
import uuid
import sqlite3
from datetime import datetime


def _get_db():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'platform', 'suncredit.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_settings(*keys, default=''):
    path = os.path.join(os.path.dirname(__file__), '..', 'launch', 'settings.json')
    try:
        with open(path) as f:
            d = json.load(f)
        for k in keys:
            d = d[k]
        return d or default
    except Exception:
        env_key = '_'.join(keys).upper()
        return os.getenv(env_key, default)


def _get_stripe():
    """Return configured stripe module or None when key missing."""
    key = _get_settings('stripe', 'secret_key') or _get_settings('STRIPE_SECRET_KEY') or os.getenv('STRIPE_SECRET_KEY', '')
    if not key:
        return None
    try:
        import stripe
        stripe.api_key = key
        return stripe
    except Exception:
        return None


def _mock_id(prefix):
    return f"{prefix}_mock_{uuid.uuid4().hex[:24]}"


# ---------- Payment Intents ----------

def create_payment_intent(amount_cents, borrower_id, loan_id, metadata=None):
    metadata = metadata or {}
    stripe = _get_stripe()
    real = False
    intent_id = _mock_id('pi')
    client_secret = _mock_id('cs')
    status = 'requires_payment_method'
    error = None

    if stripe:
        try:
            md = {'borrower_id': str(borrower_id), 'loan_id': str(loan_id)}
            md.update({k: str(v) for k, v in metadata.items()})
            pi = stripe.PaymentIntent.create(
                amount=int(amount_cents),
                currency='usd',
                metadata=md,
                automatic_payment_methods={'enabled': True},
            )
            intent_id = pi['id']
            client_secret = pi['client_secret']
            status = pi['status']
            real = True
        except Exception as e:
            error = str(e)

    # Record in payments table
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO payments (loan_id, borrower_id, amount_cents, payment_type, status, stripe_payment_intent) "
            "VALUES (?,?,?,?,?,?)",
            (loan_id, borrower_id, int(amount_cents), 'manual', 'pending', intent_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return {
        'real': real,
        'intent_id': intent_id,
        'client_secret': client_secret,
        'status': status,
        'amount_cents': int(amount_cents),
        'error': error,
    }


def confirm_payment(intent_id):
    stripe = _get_stripe()
    real = False
    status = 'succeeded'
    error = None

    if stripe and not str(intent_id).startswith('pi_mock_'):
        try:
            pi = stripe.PaymentIntent.retrieve(intent_id)
            status = pi['status']
            real = True
        except Exception as e:
            error = str(e)

    try:
        conn = _get_db()
        new_status = 'paid' if status == 'succeeded' else status
        conn.execute(
            "UPDATE payments SET status=?, paid_at=? WHERE stripe_payment_intent=?",
            (new_status, datetime.utcnow().isoformat() if new_status == 'paid' else None, intent_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return {'real': real, 'intent_id': intent_id, 'status': status, 'error': error}


# ---------- Payment Methods ----------

def get_payment_methods(borrower_id):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM payment_methods WHERE borrower_id=? ORDER BY is_default DESC, id DESC",
        (borrower_id,),
    ).fetchall()
    conn.close()
    methods = [dict(r) for r in rows]
    return {'real': bool(_get_stripe()), 'methods': methods, 'count': len(methods)}


def save_payment_method(borrower_id, stripe_pm_id, card_brand='', last4='', exp_month=0, exp_year=0):
    stripe = _get_stripe()
    real = False
    error = None

    if stripe and not str(stripe_pm_id).startswith('pm_mock_'):
        try:
            pm = stripe.PaymentMethod.retrieve(stripe_pm_id)
            card = pm.get('card') or {}
            card_brand = card_brand or card.get('brand', '')
            last4 = last4 or card.get('last4', '')
            exp_month = exp_month or card.get('exp_month', 0)
            exp_year = exp_year or card.get('exp_year', 0)
            real = True
        except Exception as e:
            error = str(e)

    conn = _get_db()
    # any existing default?
    existing = conn.execute(
        "SELECT COUNT(*) c FROM payment_methods WHERE borrower_id=?", (borrower_id,)
    ).fetchone()['c']
    is_default = 1 if existing == 0 else 0
    cur = conn.execute(
        "INSERT INTO payment_methods (borrower_id, stripe_payment_method_id, card_brand, card_last4, exp_month, exp_year, is_default) "
        "VALUES (?,?,?,?,?,?,?)",
        (borrower_id, stripe_pm_id, card_brand, last4, int(exp_month or 0), int(exp_year or 0), is_default),
    )
    pm_row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {
        'real': real,
        'id': pm_row_id,
        'stripe_payment_method_id': stripe_pm_id,
        'card_brand': card_brand,
        'last4': last4,
        'is_default': bool(is_default),
        'error': error,
    }


# ---------- Auto-Pay ----------

def setup_auto_pay(borrower_id, loan_id, payment_method_id):
    conn = _get_db()
    existing = conn.execute(
        "SELECT id FROM auto_pay WHERE borrower_id=? AND loan_id=?", (borrower_id, loan_id)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE auto_pay SET payment_method_id=?, active=1 WHERE id=?",
            (payment_method_id, existing['id']),
        )
        ap_id = existing['id']
    else:
        cur = conn.execute(
            "INSERT INTO auto_pay (borrower_id, loan_id, payment_method_id, active) VALUES (?,?,?,1)",
            (borrower_id, loan_id, payment_method_id),
        )
        ap_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {
        'real': bool(_get_stripe()),
        'id': ap_id,
        'borrower_id': borrower_id,
        'loan_id': loan_id,
        'active': True,
        'payment_method_id': payment_method_id,
    }


def cancel_auto_pay(borrower_id, loan_id):
    conn = _get_db()
    conn.execute(
        "UPDATE auto_pay SET active=0 WHERE borrower_id=? AND loan_id=?",
        (borrower_id, loan_id),
    )
    conn.commit()
    conn.close()
    return {'real': bool(_get_stripe()), 'borrower_id': borrower_id, 'loan_id': loan_id, 'active': False}


def get_auto_pay_status(borrower_id, loan_id):
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM auto_pay WHERE borrower_id=? AND loan_id=? ORDER BY id DESC LIMIT 1",
        (borrower_id, loan_id),
    ).fetchone()
    conn.close()
    if not row:
        return {'real': bool(_get_stripe()), 'active': False, 'enrolled': False}
    return {
        'real': bool(_get_stripe()),
        'active': bool(row['active']),
        'enrolled': True,
        'payment_method_id': row['payment_method_id'],
        'created_at': row['created_at'],
    }


# ---------- Webhook ----------

def process_webhook(payload, signature):
    stripe = _get_stripe()
    secret = _get_settings('stripe', 'webhook_secret') or os.getenv('STRIPE_WEBHOOK_SECRET', '')
    real = False
    event = None
    error = None

    if stripe and secret:
        try:
            event = stripe.Webhook.construct_event(payload, signature, secret)
            real = True
        except Exception as e:
            return {'real': False, 'handled': False, 'error': str(e)}
    else:
        # mock parse
        try:
            event = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
        except Exception as e:
            error = str(e)

    if not event:
        return {'real': real, 'handled': False, 'error': error or 'no event'}

    etype = event.get('type', '')
    obj = (event.get('data') or {}).get('object') or {}
    handled = False

    try:
        conn = _get_db()
        if etype == 'payment_intent.succeeded':
            conn.execute(
                "UPDATE payments SET status='paid', paid_at=? WHERE stripe_payment_intent=?",
                (datetime.utcnow().isoformat(), obj.get('id', '')),
            )
            handled = True
        elif etype == 'payment_intent.payment_failed':
            conn.execute(
                "UPDATE payments SET status='failed' WHERE stripe_payment_intent=?",
                (obj.get('id', ''),),
            )
            handled = True
        conn.execute(
            "INSERT INTO audit_logs (action_type, actor, details) VALUES (?,?,?)",
            ('stripe_webhook', 'stripe', json.dumps({'type': etype, 'id': obj.get('id', '')})),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        error = str(e)

    return {'real': real, 'handled': handled, 'event_type': etype, 'error': error}


if __name__ == '__main__':
    print(create_payment_intent(5000, 1, 1, {'note': 'cli test'}))
