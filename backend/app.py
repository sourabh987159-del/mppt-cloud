import hmac
import math
import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Optional API key. If API_KEY is NOT set, the backend stays open (so your running
# 1.0 board keeps working). Set it on Render once OTA is verified, then put the
# same key in the ESP32 sketch and in Streamlit secrets.
API_KEY = os.environ.get("API_KEY", "")

DUTY_MIN, DUTY_MAX = 10.0, 90.0
FREQ_MIN, FREQ_MAX = 10000.0, 70000.0


# ---------- models ----------
class Reading(db.Model):                      # unchanged, so no migration is needed
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    source = db.Column(db.String(20))         # "pv" (Sensor A) or "output" (Sensor B)
    voltage = db.Column(db.Float)
    current = db.Column(db.Float)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "voltage": self.voltage,
            "current": self.current,
        }


class DeviceState(db.Model):                  # new table, created automatically
    __tablename__ = "device_state"
    id = db.Column(db.Integer, primary_key=True)          # always row 1
    duty = db.Column(db.Float, nullable=False, default=10.0)
    freq = db.Column(db.Float, nullable=False, default=50000.0)
    applied = db.Column(db.Float)
    applied_freq = db.Column(db.Float)
    fw = db.Column(db.String(20))
    status = db.Column(db.String(32))
    rssi = db.Column(db.Integer)
    uptime = db.Column(db.Integer)
    last_seen = db.Column(db.DateTime(timezone=True))

    def to_dict(self):
        ls = aware(self.last_seen)
        return {
            "duty": self.duty,
            "freq": self.freq,
            "applied": self.applied,
            "applied_freq": self.applied_freq,
            "fw": self.fw,
            "status": self.status,
            "rssi": self.rssi,
            "uptime": self.uptime,
            "last_seen": ls.isoformat() if ls else None,
        }


with app.app_context():
    db.create_all()


# ---------- helpers ----------
def aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def finite(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def key_ok():
    if not API_KEY:
        return True
    return hmac.compare_digest(request.headers.get("X-API-Key", ""), API_KEY)


def require_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not key_ok():
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def get_state():
    s = db.session.get(DeviceState, 1)
    if s is None:
        try:
            s = DeviceState(id=1, duty=DUTY_MIN, freq=50000.0)   # safe duty on first boot
            db.session.add(s)
            db.session.commit()
        except Exception:
            db.session.rollback()
            s = db.session.get(DeviceState, 1)
    return s


# ---------- routes ----------
@app.route("/")
def home():
    return {"status": "ok", "message": "MPPT backend is running"}


@app.route("/data", methods=["POST"])
@require_key
def post_data():
    payload = request.get_json(silent=True) or {}
    voltage = finite(payload.get("voltage"))
    current = finite(payload.get("current")) if payload.get("current") is not None else None
    source = str(payload.get("source", "unknown"))[:20]
    if voltage is None:
        return jsonify({"error": "'voltage' must be a finite number"}), 400
    reading = Reading(source=source, voltage=voltage, current=current)
    db.session.add(reading)
    db.session.commit()
    return jsonify({"status": "stored", "id": reading.id}), 201


@app.route("/data", methods=["GET"])
def get_data():
    source = request.args.get("source")
    limit = max(1, min(request.args.get("limit", 200, type=int), 2000))
    query = Reading.query
    if source:
        query = query.filter_by(source=source)
    rows = query.order_by(Reading.timestamp.desc()).limit(limit).all()
    rows.reverse()
    return jsonify([r.to_dict() for r in rows])


@app.route("/duty", methods=["GET"])
def get_duty():
    """Dashboard reads this; the ESP32 reads it too and reports its own state in the query string."""
    s = get_state()
    applied = finite(request.args.get("applied"))
    if applied is not None and key_ok():
        applied_freq = finite(request.args.get("applied_freq"))
        fw = (request.args.get("fw", "")[:20]) or None        # old firmware sends none -> shows "--"
        status = (request.args.get("status", "")[:32]) or None
        rssi = request.args.get("rssi", type=int)
        uptime = request.args.get("uptime", type=int)

        now = datetime.now(timezone.utc)
        last = aware(s.last_seen)
        changed = (s.applied != applied or s.applied_freq != applied_freq or
                   s.fw != fw or s.status != status)
        if changed or last is None or (now - last).total_seconds() >= 3:
            s.applied, s.applied_freq = applied, applied_freq
            s.fw, s.status, s.rssi, s.uptime = fw, status, rssi, uptime
            s.last_seen = now
            db.session.commit()
    return jsonify(s.to_dict())


@app.route("/duty", methods=["POST"])
@require_key
def set_duty():
    data = request.get_json(silent=True) or {}
    if "duty" not in data and "freq" not in data:
        return jsonify({"error": "send 'duty' and/or 'freq'"}), 400

    s = get_state()
    if "duty" in data:
        d = finite(data["duty"])
        if d is None:
            return jsonify({"error": "duty must be a finite number"}), 400
        s.duty = clamp(d, DUTY_MIN, DUTY_MAX)
    if "freq" in data:
        f = finite(data["freq"])
        if f is None:
            return jsonify({"error": "freq must be a finite number"}), 400
        s.freq = clamp(f, FREQ_MIN, FREQ_MAX)
    db.session.commit()
    return jsonify(s.to_dict())


if __name__ == "__main__":
    # Local testing only. On Render run:  gunicorn app:app
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
