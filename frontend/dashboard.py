import time
import requests
import pandas as pd
import streamlit as st

BACKEND_URL = st.secrets.get("BACKEND_URL", "https://mppt-cloud-1.onrender.com")

st.set_page_config(page_title="MPPT Duty Control", layout="centered")
st.title("MPPT Duty Cycle Control")

if "history" not in st.session_state:
    st.session_state.history = []


def get_state():
    try:
        r = requests.get(f"{BACKEND_URL}/duty", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def set_duty(value):
    r = requests.post(f"{BACKEND_URL}/duty", json={"duty": value}, timeout=10)
    r.raise_for_status()
    return r.json()


# ---------- Control ----------
state = get_state()
start_val = float(state["duty"]) if state and state.get("duty") is not None else 50.0

duty = st.slider("Duty cycle (%)", 10, 90, int(round(start_val)), step=1)

if st.button("Apply duty", type="primary"):
    try:
        res = set_duty(float(duty))
        st.success(f"Sent {res['duty']:.1f} %. ESP32 picks it up within ~1-2 s.")
    except Exception as e:
        st.error(f"Could not send duty: {e}")

st.divider()


# ---------- Live status (refreshes every 2 s) ----------
@st.fragment(run_every=2)
def live_status():
    s = get_state()
    if s is None:
        st.warning("Backend not reachable (it may be waking up on Render, wait ~30 s).")
        return

    commanded = s.get("duty")
    applied = s.get("applied")
    last_seen = s.get("last_seen")

    online = False
    if last_seen:
        try:
            ts = pd.to_datetime(last_seen, utc=True)
            age = (pd.Timestamp.now(tz="UTC") - ts).total_seconds()
            online = age < 10
        except Exception:
            pass

    c1, c2, c3 = st.columns(3)
    c1.metric("Commanded duty", f"{commanded:.1f} %" if commanded is not None else "--")
    c2.metric("Applied on ESP32", f"{applied:.1f} %" if applied is not None else "--")
    c3.metric("ESP32", "Online" if online else "Offline")

    if applied is not None:
        hist = st.session_state.history
        hist.append({"time": time.strftime("%H:%M:%S"), "applied": applied})
        st.session_state.history = hist[-100:]

    if st.session_state.history:
        df = pd.DataFrame(st.session_state.history).set_index("time")
        st.line_chart(df, y="applied")
        st.caption("Applied duty (%) over time, since this page was opened.")


live_status()
