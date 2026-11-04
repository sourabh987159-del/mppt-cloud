import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)


db_url = os.environ.get("postgresql://mppt_news_user:hTFRaTpydMeo1G1xDlBjqefC3A0zFQ67@dpg-dblfj4bm8hqs7395lm60-a/mppt_news", "sqlite:///local.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Reading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    source = db.Column(db.String(20))       # "pv" (Sensor A) or "output" (Sensor B)
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


# PWM duty cycle (percent) that the ESP32 reads. Kept in memory.
duty_state = {"duty": 50.0}


@app.route("/")
def home():
    return {"status": "ok", "message": "MPPT backend is running"}


@app.route("/data", methods=["POST"])
def post_data():
    """
    ESP32 posts JSON like:
    {"source": "output", "voltage": 39.87, "current": 2.65}
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "expected JSON body"}), 400

    voltage = payload.get("voltage")
    current = payload.get("current")
    source = payload.get("source", "unknown")

    if voltage is None:
        return jsonify({"error": "missing 'voltage'"}), 400

    reading = Reading(source=source, voltage=voltage, current=current)
    db.session.add(reading)
    db.session.commit()

    return jsonify({"status": "stored", "id": reading.id}), 201


@app.route("/data", methods=["GET"])
def get_data():
    """
    Returns the most recent readings, newest last (good for plotting).
    Optional query params: ?source=output&limit=100
    """
    source = request.args.get("source")
    limit = int(request.args.get("limit", 200))

    query = Reading.query
    if source:
        query = query.filter_by(source=source)

    rows = query.order_by(Reading.timestamp.desc()).limit(limit).all()
    rows.reverse()  # oldest first, easier to plot directly

    return jsonify([r.to_dict() for r in rows])


@app.route("/duty", methods=["GET"])
def get_duty():
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
