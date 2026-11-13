import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Allows Streamlit to communicate with Flask without browser blocks

# Render database connection handling
db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Database model for MPPT Voltage/Current telemetry
class Reading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    source = db.Column(db.String(20))
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

with app.app_context():
    db.create_all()

# Expanded state dictionary matching your Streamlit frontend expectations
duty_state = {
    "duty": 50.0,
    "freq": 50000.0,        # Default 50 kHz
    "applied": None,
    "applied_freq": None,
    "last_seen": None,
    "fw": None,
    "status": None,
    "rssi": None,
    "uptime": None
}

@app.route("/")
def home():
    return {"status": "ok", "message": "MPPT backend is running"}

# ---------- Telemetry Endpoints (Database) ----------

@app.route("/data", methods=["POST"])
def post_data():
    data = request.get_json(silent=True) or {}
    try:
        r = Reading(
            source=str(data.get("source", "esp32-mppt"))[:20],
            voltage=float(data.get("voltage")),
            current=float(data.get("current", 0)),
        )
    except (TypeError, ValueError):
        return jsonify({"error": "voltage and current must be numbers"}), 400
    
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201

@app.route("/data", methods=["GET"])
def get_data():
    limit = request.args.get("limit", 200, type=int)
    q = Reading.query
    source = request.args.get("source")
    if source:
        q = q.filter_by(source=source)
    rows = q.order_by(Reading.id.desc()).limit(limit).all()
    return jsonify([r.to_dict() for r in reversed(rows)])

# ---------- Control Loop Endpoints (In-Memory State) ----------

@app.route("/duty", methods=["GET"])
def get_duty():
    # ESP32 reports its actual state as URL query parameters when it polls for updates
    applied = request.args.get("applied", type=float)
    applied_freq = request.args.get("applied_freq", type=float)
    fw = request.args.get("fw", type=str)
    status = request.args.get("status", type=str)
    rssi = request.args.get("rssi", type=int)
    uptime = request.args.get("uptime", type=int)

    # If the ESP32 provided any data, update the state and the last_seen timestamp
    if any(v is not None for v in [applied, applied_freq, fw, status, rssi, uptime]):
        duty_state["last_seen"] = datetime.now(timezone.utc).isoformat()
        if applied is not None: duty_state["applied"] = applied
        if applied_freq is not None: duty_state["applied_freq"] = applied_freq
        if fw is not None: duty_state["fw"] = fw
        if status is not None: duty_state["status"] = status
        if rssi is not None: duty_state["rssi"] = rssi
        if uptime is not None: duty_state["uptime"] = uptime

    return jsonify(duty_state)

@app.route("/duty", methods=["POST"])
def set_duty():
    # Streamlit dashboard uses this to set the commanded targets
    data = request.get_json(silent=True) or {}
    
    if "duty" in data:
        try:
            # Constrain duty cycle to 10% - 90% for boost converter safety
            duty_state["duty"] = max(10.0, min(90.0, float(data["duty"])))
        except (TypeError, ValueError):
            return jsonify({"error": "duty must be a number"}), 400
            
    if "freq" in data:
        try:
            # Constrain frequency to 10kHz - 100kHz 
            duty_state["freq"] = max(10000.0, min(100000.0, float(data["freq"])))
        except (TypeError, ValueError):
            return jsonify({"error": "freq must be a number"}), 400
            
    return jsonify(duty_state)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
