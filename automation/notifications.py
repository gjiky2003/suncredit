"""Email + SMS notifications with provider fallback to print()."""
import os
import json
import sqlite3
from datetime import datetime


BRAND = 'SunCredit'
FROM_EMAIL_DEFAULT = 'noreply@suncredit.example'


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


def _log(action, details):
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO audit_logs (action_type, actor, details) VALUES (?,?,?)",
            (action, 'notifications', json.dumps(details)[:4000]),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------- Email ----------

def send_email(to, subject, html_body):
    api_key = _get_settings('sendgrid', 'api_key') or os.getenv('SENDGRID_API_KEY', '')
    from_email = (_get_settings('sendgrid', 'from_email')
                  or os.getenv('SENDGRID_FROM_EMAIL', '')
                  or FROM_EMAIL_DEFAULT)

    if not api_key or not to:
        print(f"[EMAIL-FALLBACK] To={to} Subject={subject}")
        print(html_body[:500])
        _log('email_fallback', {'to': to, 'subject': subject})
        return {'real': False, 'sent': bool(to), 'to': to, 'subject': subject}

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        msg = Mail(from_email=from_email, to_emails=to, subject=subject, html_content=html_body)
        sg = SendGridAPIClient(api_key)
        resp = sg.send(msg)
        _log('email_sent', {'to': to, 'subject': subject, 'status': resp.status_code})
        return {'real': True, 'sent': True, 'to': to, 'subject': subject, 'status_code': resp.status_code}
    except Exception as e:
        print(f"[EMAIL-ERROR] {e} -- falling back: To={to} Subject={subject}")
        _log('email_error', {'to': to, 'subject': subject, 'error': str(e)})
        return {'real': False, 'sent': False, 'to': to, 'subject': subject, 'error': str(e)}


# ---------- SMS ----------

def send_sms(to, body):
    sid = _get_settings('twilio', 'account_sid') or os.getenv('TWILIO_ACCOUNT_SID', '')
    token = _get_settings('twilio', 'auth_token') or os.getenv('TWILIO_AUTH_TOKEN', '')
    from_number = _get_settings('twilio', 'from_number') or os.getenv('TWILIO_FROM_NUMBER', '')

    if not (sid and token and from_number) or not to:
        print(f"[SMS-FALLBACK] To={to} Body={body[:160]}")
        _log('sms_fallback', {'to': to, 'body': body[:200]})
        return {'real': False, 'sent': bool(to), 'to': to}

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(body=body, from_=from_number, to=to)
        _log('sms_sent', {'to': to, 'sid': msg.sid})
        return {'real': True, 'sent': True, 'to': to, 'sid': msg.sid}
    except Exception as e:
        print(f"[SMS-ERROR] {e} -- fallback to={to}")
        _log('sms_error', {'to': to, 'error': str(e)})
        return {'real': False, 'sent': False, 'to': to, 'error': str(e)}


# ---------- Borrower-targeted ----------

def _get_borrower(borrower_id):
    conn = _get_db()
    row = conn.execute("SELECT * FROM borrowers WHERE id=?", (borrower_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def notify_borrower(borrower_id, subject, message, channel='email'):
    b = _get_borrower(borrower_id)
    if not b:
        return {'sent': False, 'error': 'borrower_not_found'}

    if channel == 'sms':
        return send_sms(b.get('phone', ''), f"{subject}: {message}")
    html = _wrap_html(subject, f"<p>Hi {b.get('first_name','')},</p><p>{message}</p>")
    return send_email(b.get('email', ''), subject, html)


def _wrap_html(title, inner):
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px">
  <div style="max-width:600px;margin:auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e3e3e3">
    <div style="background:#0a7d3a;color:#fff;padding:16px 24px;font-size:20px;font-weight:bold">{BRAND}</div>
    <div style="padding:24px;color:#222;line-height:1.5">
      <h2 style="margin-top:0;color:#0a7d3a">{title}</h2>
      {inner}
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0"/>
      <p style="color:#888;font-size:12px">{BRAND} &middot; This is an automated message. Reply to support@suncredit.example for help.</p>
    </div>
  </div></body></html>"""


def send_payment_reminder(borrower_id, loan_id, amount_due, due_date):
    b = _get_borrower(borrower_id)
    if not b:
        return {'sent': False, 'error': 'borrower_not_found'}
    amt = f"${(amount_due/100 if amount_due > 1000 else amount_due):,.2f}" if isinstance(amount_due, (int, float)) else str(amount_due)
    inner = f"""
      <p>Hi {b.get('first_name','')},</p>
      <p>This is a friendly reminder that your loan payment is coming up.</p>
      <table style="width:100%;border-collapse:collapse;margin:16px 0">
        <tr><td style="padding:8px;background:#f9f9f9"><b>Loan #</b></td><td style="padding:8px">{loan_id}</td></tr>
        <tr><td style="padding:8px;background:#f9f9f9"><b>Amount Due</b></td><td style="padding:8px">{amt}</td></tr>
        <tr><td style="padding:8px;background:#f9f9f9"><b>Due Date</b></td><td style="padding:8px">{due_date}</td></tr>
      </table>
      <p>You can pay or enroll in AutoPay from your dashboard.</p>
    """
    subject = f"Payment Reminder — Loan #{loan_id}"
    html = _wrap_html(subject, inner)
    return send_email(b.get('email', ''), subject, html)


# Stage 0-5 collection templates
_COLLECTION_TEMPLATES = {
    0: {
        'subject': "Friendly reminder: payment due — Loan #{loan_id}",
        'tone': "We noticed your payment is a few days late. No worries — life happens.",
        'cta': "Please make a payment when you get a chance to keep your account in good standing.",
    },
    1: {
        'subject': "Your payment is overdue — Loan #{loan_id}",
        'tone': "Your payment is now {days} days past due.",
        'cta': "Please log in and bring your account current to avoid additional fees.",
    },
    2: {
        'subject': "URGENT: Loan #{loan_id} — Late fee assessed",
        'tone': "Your account is {days} days past due. A late fee has been assessed.",
        'cta': "Pay today to stop further fees and protect your credit.",
    },
    3: {
        'subject': "FINAL NOTICE — Loan #{loan_id}",
        'tone': "Your loan is {days} days past due. This is a FINAL NOTICE before further action.",
        'cta': "Contact us within 7 days to arrange payment or a hardship plan.",
    },
    4: {
        'subject': "Legal referral pending — Loan #{loan_id}",
        'tone': "Your account ({days} days past due) is being prepared for legal/3rd-party referral.",
        'cta': "Call us immediately to resolve this matter and avoid escalation.",
    },
    5: {
        'subject': "Account charged off — Loan #{loan_id}",
        'tone': "After {days} days past due, your loan has been charged off and reported.",
        'cta': "Settlement options may still be available. Contact our recovery team.",
    },
}


def send_collection_notice(borrower_id, loan_id, days_past_due, stage):
    b = _get_borrower(borrower_id)
    if not b:
        return {'sent': False, 'error': 'borrower_not_found'}
    tpl = _COLLECTION_TEMPLATES.get(int(stage), _COLLECTION_TEMPLATES[0])
    subject = tpl['subject'].format(loan_id=loan_id, days=days_past_due)
    inner = f"""
      <p>Hi {b.get('first_name','')},</p>
      <p>{tpl['tone'].format(days=days_past_due)}</p>
      <p><b>{tpl['cta']}</b></p>
      <p>Loan: <b>#{loan_id}</b> &middot; Days past due: <b>{days_past_due}</b> &middot; Stage: <b>{stage}</b></p>
    """
    html = _wrap_html(subject, inner)
    res = send_email(b.get('email', ''), subject, html)
    # also SMS for stages >= 2 if phone present
    if int(stage) >= 2 and b.get('phone'):
        send_sms(b['phone'], f"{BRAND}: {subject} — log in to resolve.")
    return res


def notify_admin(subject, message):
    admin_email = (_get_settings('admin', 'email')
                   or os.getenv('ADMIN_EMAIL', '')
                   or 'admin@suncredit.example')
    html = _wrap_html(subject, f"<p>{message}</p>")
    return send_email(admin_email, f"[{BRAND} Admin] {subject}", html)


if __name__ == '__main__':
    print(notify_admin('Test', 'Notifications module loaded.'))
