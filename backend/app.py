import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify
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

duty_state = {"duty": 50.0, "applied": None, "last_seen": None}


@app.route("/")
def home():
    return {"status": "ok", "message": "MPPT backend is running"}


@app.route("/data", methods=["POST"])
def post_data():
    data = request.get_json(silent=True) or {}
    try:
        r = Reading(
            source=str(data.get("source", "unknown"))[:20],
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


@app.route("/duty", methods=["GET"])
def get_duty():
    applied = request.args.get("applied", type=float)
    if applied is not None:
        duty_state["applied"] = applied
        duty_state["last_seen"] = datetime.now(timezone.utc).isoformat()
    return jsonify(duty_state)


@app.route("/duty", methods=["POST"])
def set_duty():
    data = request.get_json(silent=True) or {}
    try:
        d = float(data.get("duty"))
    except (TypeError, ValueError):
        return jsonify({"error": "duty must be a number"}), 400
    duty_state["duty"] = max(10.0, min(90.0, d))
    return jsonify(duty_state)
