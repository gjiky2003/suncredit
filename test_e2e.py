#!/usr/bin/env python3
"""SunCredit end-to-end test suite — verifies the full borrower + admin flow."""
import os
import sys
import subprocess

# Required env vars
os.environ.setdefault('SECRET_KEY', 'test-secret-key-32-chars-12345678901234')
os.environ.setdefault('JWT_SECRET', 'test-jwt-secret-32-chars-12345678901234')
os.environ.setdefault('ADMIN_PASSWORD', 'admin123')

PLATFORM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'platform')
sys.path.insert(0, PLATFORM_DIR)
os.chdir(PLATFORM_DIR)

# Reset DB
db_path = os.path.join(PLATFORM_DIR, 'suncredit.db')
if os.path.exists(db_path):
    os.remove(db_path)

passed = 0
failed = 0
errors = []

def check(name, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  ✗ {name} — {detail}")


from app import app
client = app.test_client()
admin = app.test_client()

# ── 1. Public pages ──
print("\n--- Public Pages ---")
r = client.get('/'); check("Landing renders", r.status_code == 200)
r = client.get('/about'); check("About page", r.status_code == 200)
r = client.get('/terms'); check("Terms page", r.status_code == 200)
r = client.get('/privacy'); check("Privacy page", r.status_code == 200)
r = client.get('/api/health')
check("Health API", r.status_code == 200, str(r.status_code))
check("Health JSON valid", b'"status":"ok"' in r.data, r.data.decode()[:100])

# ── 2. Registration ──
print("\n--- Registration ---")
r = client.get('/register'); check("Register page renders", r.status_code == 200)
r = client.post('/register', data={
    'first_name': 'Alice', 'last_name': 'Test', 
    'email': 'alice@suncredit.test', 'password': 'password123',
})
check("Register POST redirects", r.status_code == 302, str(r.status_code))

r = client.get('/dashboard')
check("Dashboard reachable after register", r.status_code == 200, str(r.status_code))
check("Dashboard shows name", b'Alice' in r.data, "name not in response")

# ── 3. Logout/Login ──
print("\n--- Login flow ---")
client.get('/logout')
r = client.get('/dashboard')
check("Dashboard requires login", r.status_code == 302)

r = client.post('/login', data={'email':'alice@suncredit.test', 'password':'password123'})
check("Login redirects to dashboard", r.status_code == 302 and '/dashboard' in (r.location or ''))

r = client.get('/dashboard')
check("Dashboard after login", r.status_code == 200)
check("Wrong password rejected", client.post('/login', data={'email':'alice@suncredit.test','password':'wrong'}).status_code == 200)

# ── 4. Application flow ──
print("\n--- Application 5 steps ---")
steps = [
    {'step':'1', 'first_name':'Alice', 'last_name':'Test', 'dob':'1992-03-14', 'ssn_last4':'1234', 'phone':'5551112222'},
    {'step':'2', 'employer_name':'Acme Co', 'employer_phone':'5550000', 'employment_status':'employed', 'employment_length_months':'48',
     'address':'123 Main', 'city':'Austin', 'state':'TX', 'zip':'78701', 'home_ownership':'rent', 'housing_payment':'1500'},
    {'step':'3', 'annual_income':'72000', 'monthly_debt':'600', 'credit_score_bucket':'good', 'utilization_bucket':'low',
     'num_derogatory':'0', 'num_credit_lines':'10', 'bank_routing':'123456789', 'bank_account':'987654321'},
    {'step':'4', 'loan_amount':'10000', 'loan_purpose':'debt_consolidation', 'term_months':'36'},
]
for i, data in enumerate(steps, 1):
    r = client.post('/apply', data=data)
    check(f"Apply step {i} POST", r.status_code == 302, f"got {r.status_code}")

r = client.post('/apply', data={'step':'5', 'confirm':'1'})
check("Apply step 5 submit", r.status_code == 200, str(r.status_code))
has_decision = any(k in r.data.lower() for k in (b'apr', b'risk', b'tier', b'approved', b'declined'))
check("Decision page rendered", has_decision)

# ── 5. Connect bank ──
print("\n--- Connect bank ---")
r = client.get('/connect-bank')
check("Connect-bank page", r.status_code == 200)
check("Has bank profiles", any(b in r.data.lower() for b in (b'chase', b'wells', b'chime')))

# ── 6. Admin flows ──
print("\n--- Admin ---")
r = admin.get('/admin/login')
check("Admin login page", r.status_code == 200)

r = admin.post('/admin/login', data={'email':'admin@suncredit.com', 'password':'admin123'})
check("Admin login POST redirects", r.status_code == 302, str(r.status_code))

r = admin.get('/admin/dashboard')
check("Admin dashboard", r.status_code == 200)

r = admin.get('/admin/applications')
check("Admin applications page", r.status_code == 200)
check("Admin sees test borrower", b'alice' in r.data.lower())

r = admin.get('/admin/borrowers')
check("Admin borrowers", r.status_code == 200)
check("Borrowers page has Alice", b'Alice' in r.data)

r = admin.get('/admin/portfolio')
check("Admin portfolio", r.status_code == 200)

# ── 7. Underwriting engine import ──
print("\n--- Underwriting Engine ---")
sys.path.insert(0, os.path.join(os.path.dirname(PLATFORM_DIR), 'underwriting'))
try:
    from scorer import LoanScorer
    s = LoanScorer()
    result = s.score_application({
        'age':30, 'annual_income':60000, 'employment_length':5, 'credit_score':720,
        'dti_ratio':0.3, 'utilization':0.2, 'num_derogatory':0, 'num_credit_lines':10,
        'home_ownership':'rent', 'loan_amount':10000, 'loan_purpose':'personal',
    })
    check("Scorer loads and runs", 'risk_score' in result and 'risk_tier' in result)
    check("Scorer returns approval decision", 'approved' in result)
    check("Scorer returns reasons", isinstance(result.get('decision_reasons'), list))
except Exception as e:
    check("Scorer", False, str(e))

# ── 8. Cash flow analyzer ──
print("\n--- Cash Flow Analyzer ---")
try:
    from cash_flow import CashFlowAnalyzer
    cfa = CashFlowAnalyzer()
    txns = cfa.generate_demo_transactions('chase_good')
    result = cfa.analyze(txns)
    check("Cash flow analyzer runs", 'cash_flow_score' in result)
    check("Cash flow score in range", 0 <= result['cash_flow_score'] <= 100)
except Exception as e:
    check("Cash flow analyzer", False, str(e))

# ── 9. Compliance modules ──
print("\n--- Compliance Modules ---")
sys.path.insert(0, os.path.join(os.path.dirname(PLATFORM_DIR), 'compliance'))
try:
    import tila, disclosures, esign, identity, state_licensing, funding_tax
    check("All compliance modules import", True)
except Exception as e:
    check("Compliance import", False, str(e))

# ── 10. Automation modules ──
print("\n--- Automation Modules ---")
sys.path.insert(0, os.path.join(os.path.dirname(PLATFORM_DIR), 'automation'))
try:
    import stripe_payments, kyc, notifications, loan_collections, autopilot
    check("All automation modules import", True)
except Exception as e:
    check("Automation import", False, str(e))

# ── 11. Security checks ──
print("\n--- Security ---")
import bcrypt
from app import hash_password, check_password
h = hash_password('test-password-123')
check("bcrypt hash format", h.startswith('$2'))
check("bcrypt verify", check_password('test-password-123', h))
check("bcrypt rejects wrong", not check_password('wrong', h))

# Auth required on sensitive APIs
client.get('/logout')
r = client.post('/api/score-application', json={'credit_score': 700})
check("Score API requires auth", r.status_code in (302, 401))

# ── Summary ──
total = passed + failed
print(f"\n{'='*60}")
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if errors:
    print("\nFailures:")
    for e in errors:
        print(f"  - {e}")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
