"""Extended routes for SunCredit — info pages + KYC/payment/niche stubs."""
from flask import render_template, jsonify, request


def register_routes(app, get_db, login_required, admin_required, audit_log,
                    hash_password, check_password, generate_jwt, decode_jwt):
    """Attach extended routes to the Flask app."""

    # ── Static info pages ──
    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    @app.route('/privacy')
    def privacy():
        return render_template('privacy.html')

    # ── KYC stubs ──
    @app.route('/kyc/start', methods=['GET', 'POST'])
    @login_required
    def kyc_start(user):
        return jsonify({
            'status': 'pending',
            'borrower_id': user['id'],
            'message': 'KYC flow stub — to be implemented',
        })

    @app.route('/kyc/status')
    @login_required
    def kyc_status(user):
        return jsonify({
            'status': user['kyc_status'] or 'pending',
            'borrower_id': user['id'],
        })

    @app.route('/kyc/upload', methods=['POST'])
    @login_required
    def kyc_upload(user):
        return jsonify({'status': 'received', 'message': 'KYC upload stub'})

    # ── Payment stubs ──
    @app.route('/payments/methods', methods=['GET', 'POST'])
    @login_required
    def payment_methods(user):
        return jsonify({'methods': [], 'message': 'Payment methods stub'})

    @app.route('/payments/pay/<int:loan_id>', methods=['POST'])
    @login_required
    def make_payment(user, loan_id):
        return jsonify({
            'status': 'pending',
            'loan_id': loan_id,
            'message': 'Payment processing stub',
        })

    @app.route('/payments/auto-pay', methods=['GET', 'POST'])
    @login_required
    def auto_pay(user):
        return jsonify({'enabled': False, 'message': 'Auto-pay stub'})

    @app.route('/payments/webhook', methods=['POST'])
    def payments_webhook():
        return jsonify({'received': True})

    # ── Niche underwriting stubs ──
    @app.route('/niche/medical', methods=['GET', 'POST'])
    @login_required
    def niche_medical(user):
        return jsonify({'product': 'medical', 'message': 'Niche medical stub'})

    @app.route('/niche/auto-repair', methods=['GET', 'POST'])
    @login_required
    def niche_auto_repair(user):
        return jsonify({'product': 'auto_repair', 'message': 'Niche auto-repair stub'})

    @app.route('/niche/rate-improvement', methods=['GET', 'POST'])
    @login_required
    def niche_rate_improvement(user):
        return jsonify({'product': 'rate_improvement', 'message': 'Rate improvement stub'})

    return app
