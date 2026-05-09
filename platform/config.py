"""SunCredit configuration loaded from environment."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class Config:
    # ── Required secrets — raises if missing ──
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY env var required. Generate: "
            "python3 -c 'import secrets; print(secrets.token_hex(32))'"
        )

    JWT_SECRET = os.getenv('JWT_SECRET')
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET env var required")

    # ── Database ──
    DATABASE = os.getenv('SUNCREDIT_DB') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'suncredit.db'
    )

    # ── Optional: Stripe ──
    STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

    # ── Optional: Email/SMS ──
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY', '')
    SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@suncredit.com')
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
    TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER', '')

    # ── Optional: KYC ──
    PERSONA_API_KEY = os.getenv('PERSONA_API_KEY', '')
    PERSONA_TEMPLATE_ID = os.getenv('PERSONA_TEMPLATE_ID', '')

    # ── Admin ──
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@suncredit.com')

    # ── JWT ──
    JWT_EXPIRY_HOURS = int(os.getenv('JWT_EXPIRY_HOURS', '168'))  # 7 days
    JWT_ALGORITHM = 'HS256'

    # ── Flask runtime ──
    DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT = int(os.getenv('FLASK_PORT', os.getenv('PORT', '8086')))

    # ── Security ──
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('FLASK_HTTPS', 'false').lower() == 'true'
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7  # 7 days
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
