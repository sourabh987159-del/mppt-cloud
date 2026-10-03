# MPPT Cloud Monitor ☀️⚡

A cloud-based monitoring solution for Maximum Power Point Tracking (MPPT) solar charge controller systems. This application stores and visualizes real-time telemetry from microcontrollers (such as ESP32) equipped with PV and output sensors.

---

## 🏗️ System Architecture

- **Backend (`/backend`)**: Built with Flask and SQLAlchemy (supporting SQLite locally and PostgreSQL in production). Accepts sensor data payloads from microcontrollers and serves telemetry endpoints.
- **Frontend (`/frontend`)**: Built with Streamlit for dynamic, real-time visualization of voltage, current, and telemetry charts for both PV panel input (Sensor A) and load/battery output (Sensor B).

---

## 🚀 Getting Started

### 1. Backend Setup (Flask REST API)

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

pip install -r requirements.txt
python app.py
```
The API server will run at `http://localhost:5000`.

#### API Endpoints
- **`GET /`**: Health check.
- **`POST /data`**: Ingest sensor readings.
  - JSON Payload: `{"source": "pv", "voltage": 18.5, "current": 2.1}`
- **`GET /data?source=pv&limit=100`**: Retrieve telemetry readings sorted chronologically.

---

## 📊 2. Frontend Setup (Streamlit Dashboard)

```bash
cd frontend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate

pip install -r requirements.txt
streamlit run dashboard.py
```

---

## 🛠️ Deploying

- **Backend**: Pre-configured with `Procfile` for Gunicorn deployment on platforms like Render or Heroku.
- **Frontend**: Can be deployed directly via Streamlit Community Cloud.
