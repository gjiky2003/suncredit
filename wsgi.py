"""WSGI entry for Render / Gunicorn. Run: gunicorn wsgi:app"""
import os, sys, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "platform", "app.py")
sys.path.insert(0, os.path.join(HERE, "platform"))
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("suncredit_app", APP_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
app = mod.app
