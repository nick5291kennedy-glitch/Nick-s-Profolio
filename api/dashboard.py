from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import build_dashboard  # noqa: E402


app = Flask(__name__)


@app.get("/api/dashboard")
def dashboard():
    return jsonify(build_dashboard())


@app.get("/")
def healthcheck():
    return jsonify({"ok": True})
