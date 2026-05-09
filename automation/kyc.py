"""KYC document verification + Stripe Identity integration."""
import os
import json
import sqlite3
import mimetypes
from datetime import datetime


REQUIRED_DOCS = ['government_id', 'proof_of_address', 'proof_of_income']
ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.pdf', '.webp', '.heic'}
ALLOWED_MIMES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/heic',
    'application/pdf',
}
MAX_BYTES = 15 * 1024 * 1024  # 15MB
MIN_BYTES = 10 * 1024  # 10KB


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
    key = _get_settings('stripe', 'secret_key') or os.getenv('STRIPE_SECRET_KEY', '')
    if not key:
        return None
    try:
        import stripe
        stripe.api_key = key
        return stripe
    except Exception:
        return None


def _check_dimensions(file_path):
    """Best-effort image dimension check; returns (ok, width, height)."""
    try:
        from PIL import Image
        with Image.open(file_path) as im:
            w, h = im.size
        return (w >= 300 and h >= 300, w, h)
    except Exception:
        return (True, 0, 0)  # cannot verify -> don't block


def verify_id_document(borrower_id, doc_type, file_path):
    issues = []
    confidence = 1.0
    verified = False

    if not file_path or not os.path.exists(file_path):
        return {
            'verified': False, 'confidence_score': 0.0,
            'issues': ['file_not_found'],
            'recommended_action': 'reupload',
        }

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ALLOWED_EXT:
        issues.append(f'unsupported_extension:{ext}')
        confidence -= 0.5

    size = os.path.getsize(file_path)
    if size > MAX_BYTES:
        issues.append('file_too_large')
        confidence -= 0.3
    elif size < MIN_BYTES:
        issues.append('file_too_small')
        confidence -= 0.4

    mime, _ = mimetypes.guess_type(file_path)
    if mime and mime not in ALLOWED_MIMES:
        issues.append(f'unsupported_mime:{mime}')
        confidence -= 0.3

    if ext in {'.jpg', '.jpeg', '.png', '.webp'}:
        ok, w, h = _check_dimensions(file_path)
        if not ok:
            issues.append(f'low_resolution:{w}x{h}')
            confidence -= 0.3

    confidence = max(0.0, min(1.0, confidence))
    verified = confidence >= 0.7 and not any(
        i.startswith(('file_not_found', 'unsupported_extension', 'file_too_large', 'file_too_small'))
        for i in issues
    )

    if verified:
        action = 'approve'
    elif confidence >= 0.4:
        action = 'manual_review'
    else:
        action = 'reupload'

    # Update kyc_documents
    try:
        conn = _get_db()
        existing = conn.execute(
            "SELECT id FROM kyc_documents WHERE borrower_id=? AND document_type=? ORDER BY id DESC LIMIT 1",
            (borrower_id, doc_type),
        ).fetchone()
        status = 'verified' if verified else ('manual_review' if action == 'manual_review' else 'rejected')
        if existing:
            conn.execute(
                "UPDATE kyc_documents SET file_path=?, verification_status=? WHERE id=?",
                (file_path, status, existing['id']),
            )
        else:
            conn.execute(
                "INSERT INTO kyc_documents (borrower_id, document_type, file_path, verification_status) VALUES (?,?,?,?)",
                (borrower_id, doc_type, file_path, status),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return {
        'verified': verified,
        'confidence_score': round(confidence, 2),
        'issues': issues,
        'recommended_action': action,
        'doc_type': doc_type,
    }


def kyc_check(borrower_id):
    conn = _get_db()
    rows = conn.execute(
        "SELECT document_type, verification_status FROM kyc_documents WHERE borrower_id=?",
        (borrower_id,),
    ).fetchall()
    conn.close()

    by_type = {}
    for r in rows:
        # keep most recent verified > pending > rejected
        cur = by_type.get(r['document_type'])
        rank = {'verified': 3, 'manual_review': 2, 'pending': 1, 'rejected': 0}
        if cur is None or rank.get(r['verification_status'], 0) > rank.get(cur, 0):
            by_type[r['document_type']] = r['verification_status']

    missing = [d for d in REQUIRED_DOCS if d not in by_type]
    rejected = [d for d, s in by_type.items() if s == 'rejected']
    pending = [d for d, s in by_type.items() if s in ('pending', 'manual_review')]

    if missing:
        status = 'missing'
    elif rejected:
        status = 'denied'
    elif pending:
        status = 'pending'
    elif all(by_type.get(d) == 'verified' for d in REQUIRED_DOCS):
        status = 'approved'
    else:
        status = 'pending'

    return {
        'status': status,
        'required_docs': REQUIRED_DOCS,
        'missing_docs': missing,
        'verifications': by_type,
    }


def auto_verify_kyc(borrower_id):
    conn = _get_db()
    b = conn.execute("SELECT * FROM borrowers WHERE id=?", (borrower_id,)).fetchone()
    if not b:
        conn.close()
        return {'approved': False, 'reason': 'borrower_not_found'}

    check = kyc_check(borrower_id)
    reasons = []
    if check['status'] != 'approved':
        reasons.append(f"docs_{check['status']}")
    if (b['credit_score'] or 0) < 600:
        reasons.append('credit_score_too_low')
    if (b['annual_income'] or 0) <= 0:
        reasons.append('no_income')
    if (b['employment_status'] or '') != 'employed':
        reasons.append('not_employed')

    approved = not reasons
    new_status = 'approved' if approved else ('denied' if 'docs_denied' in reasons else 'pending')
    conn.execute("UPDATE borrowers SET kyc_status=? WHERE id=?", (new_status, borrower_id))
    conn.execute(
        "INSERT INTO audit_logs (action_type, borrower_id, actor, details) VALUES (?,?,?,?)",
        ('kyc_auto_verify', borrower_id, 'system', json.dumps({'approved': approved, 'reasons': reasons})),
    )
    conn.commit()
    conn.close()

    return {
        'approved': approved,
        'reasons': reasons,
        'kyc_status': new_status,
        'doc_check': check,
    }


def stripe_identity_verify(borrower_id):
    stripe = _get_stripe()
    if not stripe:
        return {
            'real': False,
            'client_secret': f'vs_mock_secret_{borrower_id}',
            'session_id': f'vs_mock_{borrower_id}',
            'error': 'stripe_not_configured',
        }
    try:
        session = stripe.identity.VerificationSession.create(
            type='document',
            metadata={'borrower_id': str(borrower_id)},
        )
        return {
            'real': True,
            'client_secret': session['client_secret'],
            'session_id': session['id'],
        }
    except Exception as e:
        return {'real': False, 'error': str(e), 'client_secret': '', 'session_id': ''}


def handle_stripe_identity_completed(verification_session):
    """Webhook handler. verification_session is the Stripe object dict."""
    md = (verification_session or {}).get('metadata') or {}
    borrower_id = md.get('borrower_id')
    status = (verification_session or {}).get('status', '')
    if not borrower_id:
        return {'handled': False, 'error': 'no_borrower_id'}

    try:
        conn = _get_db()
        new_status = 'approved' if status == 'verified' else ('denied' if status == 'requires_input' else 'pending')
        conn.execute("UPDATE borrowers SET kyc_status=? WHERE id=?", (new_status, borrower_id))
        conn.execute(
            "INSERT INTO kyc_documents (borrower_id, document_type, file_path, verification_status) VALUES (?,?,?,?)",
            (borrower_id, 'stripe_identity', verification_session.get('id', ''),
             'verified' if status == 'verified' else 'rejected'),
        )
        conn.execute(
            "INSERT INTO audit_logs (action_type, borrower_id, actor, details) VALUES (?,?,?,?)",
            ('stripe_identity_completed', borrower_id, 'stripe',
             json.dumps({'status': status, 'session_id': verification_session.get('id', '')})),
        )
        conn.commit()
        conn.close()
        return {'handled': True, 'borrower_id': int(borrower_id), 'kyc_status': new_status}
    except Exception as e:
        return {'handled': False, 'error': str(e)}


if __name__ == '__main__':
    import sys
    bid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(json.dumps(kyc_check(bid), indent=2))
