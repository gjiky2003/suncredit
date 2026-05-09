"""SunCredit Flask web application core.

Borrower auth, 5-step application form, dashboards, admin console,
plus a small JSON API for scoring + cash-flow lookup.
"""
import os
import sys
import json
import uuid
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, date
from functools import wraps
from pathlib import Path

import bcrypt
import jwt
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort
)
from werkzeug.utils import secure_filename  # noqa: F401  (used by extended routes)

# ── Path setup so underwriting/ + automation/ are importable ──
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_ROOT / 'underwriting'))
sys.path.insert(0, str(_ROOT / 'automation'))

from config import Config  # noqa: E402
from models import get_db, init_db, audit_log  # noqa: E402

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
log = logging.getLogger('suncredit')

# Initialize DB at import time (idempotent — CREATE TABLE IF NOT EXISTS)
try:
    init_db()
except Exception as _e:
    log.warning("init_db at import failed: %s", _e)


# ─────────────────────────────────────────────────────────────────────
# Password + JWT helpers
# ─────────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')


def _legacy_sha256(password: str) -> str:
    salt = (Config.JWT_SECRET or '')[:16]
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()


def check_password(password: str, stored_hash: str) -> bool:
    """Verify password — bcrypt for new hashes, legacy SHA-256 fallback."""
    if not stored_hash:
        return False
    try:
        if stored_hash.startswith(('$2a$', '$2b$', '$2y$')):
            return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception:
        return False
    try:
        return _legacy_sha256(password) == stored_hash
    except Exception:
        return False


# Backwards-compatible aliases
verify_password = check_password


def generate_jwt(uid: int, email: str, role: str = 'borrower') -> str:
    import time as _time
    now_ts = int(_time.time())
    payload = {
        'uid': uid,
        'email': email,
        'role': role,
        'iat': now_ts - 5,
        'exp': now_ts + (Config.JWT_EXPIRY_HOURS * 3600),
        'jti': uuid.uuid4().hex,
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)


issue_jwt = generate_jwt


def decode_jwt(token: str):
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM], leeway=10)
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError as e:
        log.warning("JWT decode failed: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────
def current_user():
    token = session.get('token')
    if not token:
        return None
    payload = decode_jwt(token)
    if not payload or payload.get('role') != 'borrower':
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM borrowers WHERE id = ?", (payload['uid'],)).fetchone()
    conn.close()
    return row


def current_admin():
    token = session.get('admin_token')
    if not token:
        return None
    payload = decode_jwt(token)
    if not payload or payload.get('role') != 'admin':
        return None
    return payload


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(user, *args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        admin = current_admin()
        if not admin:
            return redirect(url_for('admin_login', next=request.path))
        return f(admin, *args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────
# Underwriting helpers
# ─────────────────────────────────────────────────────────────────────
_SCORER = None
_CF_ANALYZER = None


def get_scorer():
    global _SCORER
    if _SCORER is None:
        try:
            from scorer import LoanScorer  # type: ignore
            _SCORER = LoanScorer()
        except Exception as e:
            log.warning("LoanScorer unavailable: %s", e)
            _SCORER = False
    return _SCORER or None


def get_cash_flow_analyzer():
    global _CF_ANALYZER
    if _CF_ANALYZER is None:
        try:
            from cash_flow import CashFlowAnalyzer  # type: ignore
            _CF_ANALYZER = CashFlowAnalyzer()
        except Exception as e:
            log.warning("CashFlowAnalyzer unavailable: %s", e)
            _CF_ANALYZER = False
    return _CF_ANALYZER or None


def score_application(app_data: dict, cash_flow_data: dict | None = None):
    s = get_scorer()
    if s is not None:
        try:
            return s.score_application(app_data, cash_flow_data=cash_flow_data)
        except Exception as e:
            log.exception("scorer failed: %s", e)
    # Conservative default
    return {
        'risk_score': 100,
        'risk_tier': 'E',
        'interest_rate': 0.0,
        'monthly_payment': 0.0,
        'origination_fee': 0.0,
        'approved': False,
        'decision_reasons': ['Scorer unavailable; manual review required.'],
    }


def amortization_schedule(principal: float, apr: float, months: int):
    """Return list of (n, due_date, payment, principal, interest, balance) tuples."""
    if months <= 0 or principal <= 0:
        return []
    r = (apr or 0.0) / 12.0
    if r == 0:
        m = principal / months
    else:
        m = principal * (r * (1 + r) ** months) / (((1 + r) ** months) - 1)
    bal = principal
    today = date.today()
    out = []
    for i in range(1, months + 1):
        interest = bal * r
        princ = m - interest
        bal = max(0.0, bal - princ)
        due = (today + timedelta(days=30 * i)).isoformat()
        out.append((i, due, round(m, 2), round(princ, 2), round(interest, 2), round(bal, 2)))
    return out


def _save_payment_schedule(conn, loan_id: int, schedule):
    for (n, due, pay, pr, intr, bal) in schedule:
        conn.execute(
            "INSERT INTO payment_schedules "
            "(loan_id, payment_number, due_date, amount_cents, principal_cents, "
            " interest_cents, remaining_balance_cents, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
            (loan_id, n, due,
             int(round(pay * 100)), int(round(pr * 100)),
             int(round(intr * 100)), int(round(bal * 100)))
        )


def _coerce_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _coerce_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────
# Bootstrap admin
# ─────────────────────────────────────────────────────────────────────
def _bootstrap_admin():
    conn = get_db()
    email = Config.ADMIN_EMAIL
    row = conn.execute("SELECT id FROM admin_users WHERE email = ?", (email,)).fetchone()
    if row:
        conn.close()
        return
    pw = os.getenv('ADMIN_PASSWORD')
    generated = False
    if not pw:
        pw = secrets.token_urlsafe(16)
        generated = True
    conn.execute(
        "INSERT INTO admin_users (email, password_hash) VALUES (?, ?)",
        (email, hash_password(pw)),
    )
    conn.commit()
    conn.close()
    if generated:
        log.warning("=" * 60)
        log.warning("ADMIN BOOTSTRAP — generated password (save it now)")
        log.warning("  email:    %s", email)
        log.warning("  password: %s", pw)
        log.warning("=" * 60)
    else:
        log.info("Admin user bootstrapped from ADMIN_PASSWORD env: %s", email)


# ─────────────────────────────────────────────────────────────────────
# Build app
# ─────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = Config.SESSION_COOKIE_SECURE
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────
# Public routes
# ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('landing.html', user=current_user())


# ── Borrower auth ──
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        first_name = (request.form.get('first_name') or '').strip()
        last_name = (request.form.get('last_name') or '').strip()

        if not (email and password and first_name and last_name):
            flash('All fields are required.', 'danger')
            return render_template('register.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('register.html')

        conn = get_db()
        existing = conn.execute("SELECT id FROM borrowers WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash('An account with that email already exists.', 'danger')
            return render_template('register.html')

        cur = conn.execute(
            "INSERT INTO borrowers (email, password_hash, first_name, last_name) "
            "VALUES (?, ?, ?, ?)",
            (email, hash_password(password), first_name, last_name),
        )
        uid = cur.lastrowid
        conn.commit()
        conn.close()

        audit_log('borrower_registered', borrower_id=uid,
                  details={'email': email}, ip_address=request.remote_addr or '')
        session['token'] = generate_jwt(uid, email, role='borrower')
        flash('Welcome to SunCredit!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        conn = get_db()
        row = conn.execute("SELECT * FROM borrowers WHERE email = ?", (email,)).fetchone()
        if not row or not check_password(password, row['password_hash']):
            conn.close()
            flash('Invalid email or password.', 'danger')
            return render_template('login.html')

        conn.execute("UPDATE borrowers SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (row['id'],))
        conn.commit()
        conn.close()

        session['token'] = generate_jwt(row['id'], row['email'], role='borrower')
        audit_log('borrower_login', borrower_id=row['id'], ip_address=request.remote_addr or '')
        nxt = request.args.get('next') or url_for('dashboard')
        return redirect(nxt)

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('token', None)
    session.pop('app_data', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ── Borrower dashboard ──
@app.route('/dashboard')
@login_required
def dashboard(user):
    conn = get_db()
    apps = conn.execute(
        "SELECT * FROM applications WHERE borrower_id = ? ORDER BY created_at DESC",
        (user['id'],)
    ).fetchall()
    loans = conn.execute(
        "SELECT * FROM loans WHERE borrower_id = ? AND status='active' ORDER BY created_at DESC",
        (user['id'],)
    ).fetchall()
    payments = conn.execute(
        "SELECT * FROM payments WHERE borrower_id = ? ORDER BY created_at DESC LIMIT 25",
        (user['id'],)
    ).fetchall()
    conn.close()
    return render_template('dashboard.html', user=user, applications=apps,
                           loans=loans, payments=payments)


# ─────────────────────────────────────────────────────────────────────
# 5-step Application form (session['app_data'])
# ─────────────────────────────────────────────────────────────────────
APP_STEPS = {
    1: ['first_name', 'last_name', 'dob', 'ssn_last4', 'phone'],
    2: ['employer_name', 'employer_phone', 'employment_status',
        'employment_length_months', 'address', 'city', 'state', 'zip',
        'home_ownership', 'housing_payment'],
    3: ['annual_income', 'monthly_debt', 'credit_score_bucket',
        'utilization_bucket', 'num_derogatory', 'num_credit_lines',
        'bank_routing', 'bank_account'],
    4: ['loan_amount', 'loan_purpose', 'term_months'],
}

CREDIT_SCORE_BUCKETS = {
    'excellent': 780, 'good': 720, 'fair': 670, 'poor': 600, 'bad': 540,
}
UTILIZATION_BUCKETS = {
    'low': 0.10, 'medium': 0.35, 'high': 0.70, 'maxed': 0.95,
}


def _app_data():
    if 'app_data' not in session:
        session['app_data'] = {'step': 1}
    return session['app_data']


@app.route('/apply', methods=['GET', 'POST'])
@login_required
def apply(user):
    data = _app_data()
    step = int(request.values.get('step') or data.get('step', 1))
    step = max(1, min(5, step))

    if request.method == 'POST':
        if step in APP_STEPS:
            for field in APP_STEPS[step]:
                data[field] = (request.form.get(field) or '').strip()
            data['step'] = min(step + 1, 5)
            session['app_data'] = data
            session.modified = True
            return redirect(url_for('apply', step=data['step']))

        # Step 5: review + submit
        if step == 5 and request.form.get('confirm') == '1':
            return _submit_application(user, data)

    return render_template('apply.html', user=user, step=step, data=data)


def _submit_application(user, data: dict):
    """Persist borrower profile, run scorer, create application + loan."""
    conn = get_db()

    first = data.get('first_name') or user['first_name']
    last = data.get('last_name') or user['last_name']

    # Update borrower with profile fields
    conn.execute(
        "UPDATE borrowers SET first_name=?, last_name=?, phone=?, date_of_birth=?, "
        "ssn_last4=?, address=?, city=?, state=?, zip_code=?, home_ownership=?, "
        "employment_status=?, employer_name=?, employer_phone=?, "
        "employment_length_months=?, housing_payment=?, annual_income=? "
        "WHERE id = ?",
        (
            first, last,
            data.get('phone', ''), data.get('dob', ''), data.get('ssn_last4', ''),
            data.get('address', ''), data.get('city', ''), data.get('state', ''),
            data.get('zip', ''), data.get('home_ownership', 'rent'),
            data.get('employment_status', 'employed'),
            data.get('employer_name', ''), data.get('employer_phone', ''),
            _coerce_int(data.get('employment_length_months')),
            _coerce_float(data.get('housing_payment')),
            _coerce_float(data.get('annual_income')),
            user['id'],
        )
    )

    annual_income = _coerce_float(data.get('annual_income'))
    monthly_debt = _coerce_float(data.get('monthly_debt'))
    monthly_income = annual_income / 12.0 if annual_income else 0.0
    dti = (monthly_debt / monthly_income) if monthly_income > 0 else 0.0
    credit_score = CREDIT_SCORE_BUCKETS.get(data.get('credit_score_bucket', ''), 650)
    utilization = UTILIZATION_BUCKETS.get(data.get('utilization_bucket', ''), 0.35)

    # Build ML inputs
    ml_inputs = {
        'annual_income': annual_income,
        'monthly_debt': monthly_debt,
        'monthly_income': monthly_income,
        'dti_ratio': dti,
        'credit_score': credit_score,
        'credit_score_bucket': data.get('credit_score_bucket', ''),
        'credit_utilization': utilization,
        'utilization_bucket': data.get('utilization_bucket', ''),
        'num_derogatory': _coerce_int(data.get('num_derogatory')),
        'num_credit_lines': _coerce_int(data.get('num_credit_lines')),
        'employment_length_months': _coerce_int(data.get('employment_length_months')),
        'employment_status': data.get('employment_status', 'employed'),
        'home_ownership': data.get('home_ownership', 'rent'),
        'housing_payment': _coerce_float(data.get('housing_payment')),
        'loan_amount': _coerce_float(data.get('loan_amount')),
        'loan_purpose': data.get('loan_purpose', 'other'),
        'term_months': _coerce_int(data.get('term_months'), 36),
        'state': data.get('state', ''),
    }

    cash_flow_data = None
    cf_raw = user['cash_flow_data'] if user['cash_flow_data'] else ''
    if cf_raw and cf_raw != '{}':
        try:
            cash_flow_data = json.loads(cf_raw)
        except Exception:
            cash_flow_data = None

    decision = score_application(ml_inputs, cash_flow_data=cash_flow_data)

    approved = bool(decision.get('approved'))
    risk_score = int(decision.get('risk_score', 0) or 0)
    risk_tier = decision.get('risk_tier', '')
    interest_rate = float(decision.get('interest_rate', 0) or 0)
    monthly_payment = float(decision.get('monthly_payment', 0) or 0)
    origination_fee = float(decision.get('origination_fee', 0) or 0)

    cur = conn.execute(
        "INSERT INTO applications "
        "(borrower_id, loan_amount, loan_purpose, term_months, bank_routing, bank_account, "
        " risk_score, risk_tier, interest_rate, monthly_payment, origination_fee, "
        " status, decision_explanation, submitted_at, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (
            user['id'],
            _coerce_float(data.get('loan_amount')),
            data.get('loan_purpose', 'other'),
            _coerce_int(data.get('term_months'), 36),
            data.get('bank_routing', ''),
            data.get('bank_account', ''),
            risk_score, risk_tier, interest_rate, monthly_payment, origination_fee,
            'approved' if approved else 'declined',
            json.dumps(decision),
        )
    )
    app_id = cur.lastrowid
    loan_id = None

    if approved:
        principal = _coerce_float(data.get('loan_amount'))
        term_months = _coerce_int(data.get('term_months'), 36)
        cur2 = conn.execute(
            "INSERT INTO loans "
            "(application_id, borrower_id, principal, interest_rate, term_months, "
            " monthly_payment, origination_fee, remaining_balance, status, "
            " disbursed_at, next_payment_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, ?)",
            (
                app_id, user['id'], principal, interest_rate, term_months,
                monthly_payment, origination_fee, principal,
                (date.today() + timedelta(days=30)).isoformat(),
            )
        )
        loan_id = cur2.lastrowid
        schedule = amortization_schedule(principal, interest_rate, term_months)
        _save_payment_schedule(conn, loan_id, schedule)

    conn.commit()
    conn.close()

    audit_log(
        'application_submitted',
        borrower_id=user['id'],
        details={'app_id': app_id, 'approved': approved, 'risk_tier': risk_tier},
        ip_address=request.remote_addr or '',
    )

    session.pop('app_data', None)
    return render_template(
        'decision.html',
        user=user, decision=decision, approved=approved,
        application_id=app_id, loan_id=loan_id, data=data,
    )


# ─────────────────────────────────────────────────────────────────────
# Connect Bank — cash-flow underwriting (5 sample profiles)
# ─────────────────────────────────────────────────────────────────────
BANK_PROFILES = {
    'chase_good':   {'name': 'Chase — Strong',     'description': 'Steady $3.2K paychecks, low utilization'},
    'wells_avg':    {'name': 'Wells — Average',    'description': 'Typical W-2 with one overdraft'},
    'bofa_thin':    {'name': 'BofA — Thin File',   'description': 'Younger borrower, modest income'},
    'us_bank_gig':  {'name': 'US Bank — Gig',      'description': 'Variable gig income, weekly deposits'},
    'chime_risky':  {'name': 'Chime — Risky',      'description': 'Frequent overdrafts + NSF fees'},
}


@app.route('/connect-bank', methods=['GET', 'POST'])
@login_required
def connect_bank(user):
    if request.method == 'POST':
        profile = request.form.get('profile') or ''
        if profile not in BANK_PROFILES:
            flash('Please choose a sample bank profile.', 'danger')
            return render_template('connect_bank.html', profiles=BANK_PROFILES, user=user)

        analyzer = get_cash_flow_analyzer()
        cf_data = {}
        cf_score = 0
        if analyzer is not None:
            try:
                txns = analyzer.generate_demo_transactions(profile)
                cf_data = analyzer.analyze(txns)
                cf_score = int(round(float(cf_data.get('cash_flow_score', 0))))
                cf_data['profile'] = profile
            except Exception as e:
                log.exception("cash flow analyze failed: %s", e)
                cf_data = {'profile': profile, 'error': str(e)}
        else:
            cf_data = {'profile': profile, 'note': 'analyzer unavailable'}

        conn = get_db()
        conn.execute(
            "UPDATE borrowers SET cash_flow_data = ?, cash_flow_score = ? WHERE id = ?",
            (json.dumps(cf_data), cf_score, user['id']),
        )
        conn.commit()
        conn.close()

        audit_log('bank_connected', borrower_id=user['id'],
                  details={'profile': profile, 'score': cf_score},
                  ip_address=request.remote_addr or '')
        flash(f'Bank connected. Cash-flow score: {cf_score}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('connect_bank.html', profiles=BANK_PROFILES, user=user)


# ── Loan detail ──
@app.route('/loan/<int:loan_id>')
@login_required
def loan_detail(user, loan_id):
    conn = get_db()
    loan = conn.execute(
        "SELECT * FROM loans WHERE id = ? AND borrower_id = ?",
        (loan_id, user['id'])
    ).fetchone()
    if not loan:
        conn.close()
        abort(404)
    schedule = conn.execute(
        "SELECT * FROM payment_schedules WHERE loan_id = ? ORDER BY payment_number",
        (loan_id,)
    ).fetchall()
    payments = conn.execute(
        "SELECT * FROM payments WHERE loan_id = ? ORDER BY created_at DESC",
        (loan_id,)
    ).fetchall()
    conn.close()
    return render_template('loan_detail.html', user=user, loan=loan,
                           schedule=schedule, payments=payments)


# ─────────────────────────────────────────────────────────────────────
# Admin
# ─────────────────────────────────────────────────────────────────────
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        conn = get_db()
        row = conn.execute("SELECT * FROM admin_users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if not row or not check_password(password, row['password_hash']):
            flash('Invalid admin credentials.', 'danger')
            return render_template('admin_login.html')
        session['admin_token'] = generate_jwt(row['id'], row['email'], role='admin')
        audit_log('admin_login', actor=email, ip_address=request.remote_addr or '')
        return redirect(request.args.get('next') or url_for('admin_dashboard'))
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_token', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard(admin):
    conn = get_db()
    stats = {
        'borrowers': conn.execute("SELECT COUNT(*) c FROM borrowers").fetchone()['c'],
        'applications': conn.execute("SELECT COUNT(*) c FROM applications").fetchone()['c'],
        'total_loans': conn.execute("SELECT COUNT(*) c FROM loans").fetchone()['c'],
        'active': conn.execute("SELECT COUNT(*) c FROM loans WHERE status='active'").fetchone()['c'],
        'overdue': conn.execute(
            "SELECT COUNT(*) c FROM loans WHERE status='active' AND next_payment_date < date('now')"
        ).fetchone()['c'],
        'portfolio_value': conn.execute(
            "SELECT COALESCE(SUM(remaining_balance), 0) s FROM loans WHERE status='active'"
        ).fetchone()['s'],
        'pending': conn.execute(
            "SELECT COUNT(*) c FROM applications WHERE status IN ('submitted','draft','under_review')"
        ).fetchone()['c'],
        'approved': conn.execute("SELECT COUNT(*) c FROM applications WHERE status='approved'").fetchone()['c'],
        'declined': conn.execute("SELECT COUNT(*) c FROM applications WHERE status='declined'").fetchone()['c'],
    }
    recent_apps = conn.execute(
        "SELECT a.*, b.first_name, b.last_name, b.email "
        "FROM applications a JOIN borrowers b ON a.borrower_id = b.id "
        "ORDER BY a.created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template('admin_dash.html', admin=admin, stats=stats, recent_apps=recent_apps)


@app.route('/admin/portfolio')
@admin_required
def admin_portfolio(admin):
    conn = get_db()
    loans = conn.execute(
        "SELECT l.*, b.first_name, b.last_name, b.email "
        "FROM loans l JOIN borrowers b ON l.borrower_id = b.id "
        "ORDER BY l.created_at DESC"
    ).fetchall()
    # Tier distribution for chart
    tiers = conn.execute(
        "SELECT a.risk_tier, COUNT(*) c, COALESCE(SUM(l.principal),0) p "
        "FROM loans l JOIN applications a ON l.application_id = a.id "
        "GROUP BY a.risk_tier"
    ).fetchall()
    conn.close()
    return render_template('admin_portfolio.html', admin=admin, loans=loans, tiers=tiers)


@app.route('/admin/loan/<int:loan_id>')
@admin_required
def admin_loan_detail(admin, loan_id):
    conn = get_db()
    loan = conn.execute(
        "SELECT l.*, b.first_name, b.last_name, b.email "
        "FROM loans l JOIN borrowers b ON l.borrower_id = b.id WHERE l.id = ?",
        (loan_id,)
    ).fetchone()
    if not loan:
        conn.close()
        abort(404)
    schedule = conn.execute(
        "SELECT * FROM payment_schedules WHERE loan_id = ? ORDER BY payment_number",
        (loan_id,)
    ).fetchall()
    payments = conn.execute(
        "SELECT * FROM payments WHERE loan_id = ? ORDER BY created_at DESC",
        (loan_id,)
    ).fetchall()
    conn.close()
    return render_template('admin_loan_detail.html', admin=admin, loan=loan,
                           schedule=schedule, payments=payments)


@app.route('/admin/applications')
@admin_required
def admin_applications(admin):
    conn = get_db()
    apps = conn.execute(
        "SELECT a.*, b.first_name, b.last_name, b.email, (b.first_name || ' ' || b.last_name) AS borrower_name "
        "FROM applications a JOIN borrowers b ON a.borrower_id = b.id "
        "ORDER BY a.created_at DESC"
    ).fetchall()
    conn.close()
    filters = {
        'status': request.args.get('status', 'all'),
        'date_from': request.args.get('date_from', ''),
        'date_to': request.args.get('date_to', ''),
        'min_amount': request.args.get('min_amount', ''),
        'max_amount': request.args.get('max_amount', ''),
    }
    return render_template('admin_applications.html', admin=admin, applications=apps, filters=filters)


@app.route('/admin/borrowers')
@admin_required
def admin_borrowers(admin):
    q = (request.args.get('q') or '').strip()
    conn = get_db()
    sql = (
        "SELECT b.*, "
        "       (b.first_name || ' ' || b.last_name) AS name, "
        "       (SELECT COUNT(*) FROM applications a WHERE a.borrower_id = b.id) AS app_count, "
        "       (SELECT COUNT(*) FROM loans l WHERE l.borrower_id = b.id) AS total_loans, "
        "       (SELECT COALESCE(SUM(l.principal),0) FROM loans l WHERE l.borrower_id = b.id) AS total_borrowed "
        "FROM borrowers b "
    )
    params = ()
    if q:
        sql += "WHERE b.first_name LIKE ? OR b.last_name LIKE ? OR b.email LIKE ? OR b.phone LIKE ? "
        like = f"%{q}%"
        params = (like, like, like, like)
    sql += "ORDER BY b.created_at DESC"
    borrowers = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template('admin_borrowers.html', admin=admin, borrowers=borrowers, search_query=q)


@app.route('/admin/approve/<int:app_id>', methods=['POST'])
@admin_required
def admin_approve(admin, app_id):
    conn = get_db()
    a = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not a:
        conn.close()
        abort(404)
    conn.execute(
        "UPDATE applications SET status='approved', decided_at=CURRENT_TIMESTAMP WHERE id = ?",
        (app_id,)
    )
    existing = conn.execute("SELECT id FROM loans WHERE application_id = ?", (app_id,)).fetchone()
    if not existing and a['loan_amount'] and a['term_months']:
        cur = conn.execute(
            "INSERT INTO loans "
            "(application_id, borrower_id, principal, interest_rate, term_months, "
            " monthly_payment, origination_fee, remaining_balance, status, "
            " disbursed_at, next_payment_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP, ?)",
            (
                app_id, a['borrower_id'], a['loan_amount'], a['interest_rate'], a['term_months'],
                a['monthly_payment'], a['origination_fee'], a['loan_amount'],
                (date.today() + timedelta(days=30)).isoformat(),
            )
        )
        loan_id = cur.lastrowid
        schedule = amortization_schedule(a['loan_amount'], a['interest_rate'], a['term_months'])
        _save_payment_schedule(conn, loan_id, schedule)

    conn.commit()
    conn.close()
    audit_log('application_approved', borrower_id=a['borrower_id'],
              actor=admin.get('email', 'admin'),
              details={'app_id': app_id}, ip_address=request.remote_addr or '')
    flash('Application approved.', 'success')
    return redirect(url_for('admin_applications'))


@app.route('/admin/decline/<int:app_id>', methods=['POST'])
@admin_required
def admin_decline(admin, app_id):
    conn = get_db()
    a = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not a:
        conn.close()
        abort(404)
    conn.execute(
        "UPDATE applications SET status='declined', decided_at=CURRENT_TIMESTAMP WHERE id = ?",
        (app_id,)
    )
    conn.commit()
    conn.close()
    audit_log('application_declined', borrower_id=a['borrower_id'],
              actor=admin.get('email', 'admin'),
              details={'app_id': app_id}, ip_address=request.remote_addr or '')
    flash('Application declined.', 'info')
    return redirect(url_for('admin_applications'))


# ─────────────────────────────────────────────────────────────────────
# JSON API
# ─────────────────────────────────────────────────────────────────────
@app.route('/api/health')
def api_health():
    return jsonify({'status': 'ok', 'service': 'suncredit',
                    'time': datetime.utcnow().isoformat() + 'Z'})


@app.route('/api/score-application', methods=['POST'])
@login_required
def api_score_application(user):
    payload = request.get_json(silent=True) or {}
    cf_data = None
    cf_raw = user['cash_flow_data'] if user['cash_flow_data'] else ''
    if cf_raw and cf_raw != '{}':
        try:
            cf_data = json.loads(cf_raw)
        except Exception:
            cf_data = None
    decision = score_application(payload, cash_flow_data=cf_data)
    return jsonify(decision)


@app.route('/api/cash-flow-score')
@login_required
def api_cash_flow_score(user):
    cf_raw = user['cash_flow_data'] if user['cash_flow_data'] else '{}'
    try:
        cf_data = json.loads(cf_raw)
    except Exception:
        cf_data = {}
    return jsonify({
        'score': user['cash_flow_score'] or 0,
        'connected': bool(cf_data) and cf_data != {},
        'data': cf_data,
    })


# ─────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def _404(e):
    try:
        return render_template('404.html'), 404
    except Exception:
        return jsonify({'error': 'not_found'}), 404


@app.errorhandler(500)
def _500(e):
    log.exception("server error: %s", e)
    try:
        return render_template('500.html'), 500
    except Exception:
        return jsonify({'error': 'server_error'}), 500


# ─────────────────────────────────────────────────────────────────────
# Register extended routes (about, terms, privacy, KYC/payment stubs)
# ─────────────────────────────────────────────────────────────────────
from routes.extended import register_routes  # noqa: E402

register_routes(
    app, get_db, login_required, admin_required, audit_log,
    hash_password, check_password, generate_jwt, decode_jwt,
)

# Bootstrap admin user at import time (idempotent)
try:
    _bootstrap_admin()
except Exception as _e:
    log.warning("Admin bootstrap failed: %s", _e)


# ─────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    _bootstrap_admin()
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', '8085'))
    app.run(debug=debug, host=host, port=port)
