import time

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="MPPT Control", layout="wide")


def secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


BACKEND_URL = secret("BACKEND_URL", "https://mppt-cloud-1.onrender.com")
API_KEY = secret("API_KEY", "")
ss = st.session_state


def get_state(timeout=3):
    try:
        r = requests.get(f"{BACKEND_URL}/duty", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def send(payload):
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    r = requests.post(f"{BACKEND_URL}/duty", json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


# ---------- session setup ----------
ss.setdefault("history", [])
ss.setdefault("events", [])
ss.setdefault("prev", {})
ss.setdefault("flash", None)

if "duty_slider" not in ss:
    first = get_state(timeout=10)            # allows for a Render cold start, once
    ss.duty_slider = int(round(first["duty"])) if first and first.get("duty") is not None else 10
    ss.freq_slider = int(round(first["freq"] / 1000)) if first and first.get("freq") is not None else 50


def log(msg):
    ss.events.insert(0, f"{time.strftime('%H:%M:%S')}  {msg}")
    del ss.events[50:]


# ---------- button callbacks (run before the page redraws, so they may set slider values) ----------
def do_apply():
    try:
        res = send({"duty": float(ss.duty_slider), "freq": float(ss.freq_slider) * 1000})
        ss.flash = ("ok", f"Sent {res['duty']:.1f} % at {res['freq'] / 1000:.0f} kHz. "
                          "The ESP32 picks it up within 1-2 s.")
        log(f"You sent {res['duty']:.1f} % / {res['freq'] / 1000:.0f} kHz")
    except Exception as e:
        ss.flash = ("err", f"Could not send: {e}")


def do_preset(duty):
    ss.duty_slider = duty
    do_apply()


# ---------- layout ----------
st.title("MPPT control")
left, right = st.columns([1, 2], gap="large")

with left:
    st.subheader("Set output")
    st.slider("Duty cycle (%)", 10, 90, step=1, key="duty_slider")
    st.slider("PWM frequency (kHz)", 10, 70, step=1, key="freq_slider")
    st.button("Apply", type="primary", on_click=do_apply, use_container_width=True)

    st.caption("Quick duty presets (keep the current frequency)")
    p1, p2, p3, p4 = st.columns(4)
    p1.button("10 %", on_click=do_preset, args=(10,), use_container_width=True)
    p2.button("25 %", on_click=do_preset, args=(25,), use_container_width=True)
    p3.button("50 %", on_click=do_preset, args=(50,), use_container_width=True)
    p4.button("75 %", on_click=do_preset, args=(75,), use_container_width=True)

    if ss.flash:
        kind, msg = ss.flash
        (st.success if kind == "ok" else st.error)(msg)


@st.fragment(run_every=2)
def live():
    s = get_state()
    if s is None:
        st.warning("Backend not reachable. If it is waking up on Render, wait about 30 s.")
        return

    duty, freq = s.get("duty"), s.get("freq")
    applied, applied_freq = s.get("applied"), s.get("applied_freq")
    fw, status = s.get("fw"), s.get("status")

    online, age = False, None
    if s.get("last_seen"):
        try:
            ts = pd.to_datetime(s["last_seen"], utc=True)
            age = (pd.Timestamp.now(tz="UTC") - ts).total_seconds()
            online = age < 10
        except Exception:
            pass

    if online and status == "updating":
        device = "Downloading update"
    elif not online and status == "updating":
        device = "Rebooting after update"
    elif online and status == "update_failed":
        device = "Online (update failed)"
    elif online:
        device = "Online"
    else:
        device = "Offline"

    # ----- event log: what changed since the last refresh -----
    prev = ss.prev
    if not prev:
        log("Dashboard connected")
    else:
        if online != prev["online"]:
            log("ESP32 came online" if online else "ESP32 went offline")
        if fw != prev["fw"]:
            log(f"Firmware changed: {prev['fw'] or '--'} -> {fw or '--'}")
        if status != prev["status"] and status:
            log(f"Device status: {status}")
        if applied != prev["applied"] and applied is not None:
            log(f"ESP32 applied {applied:.1f} %")
        if applied_freq != prev["applied_freq"] and applied_freq is not None:
            log(f"ESP32 applied {applied_freq / 1000:.0f} kHz")
    ss.prev = {"online": online, "fw": fw, "status": status,
               "applied": applied, "applied_freq": applied_freq}

    # ----- chart history -----
    nan = float("nan")
    ss.history.append({
        "time": time.strftime("%H:%M:%S"),
        "Commanded duty (%)": duty if duty is not None else nan,
        "Applied duty (%)": applied if applied is not None else nan,
        "Commanded freq (kHz)": freq / 1000 if freq is not None else nan,
        "Applied freq (kHz)": applied_freq / 1000 if applied_freq is not None else nan,
    })
    del ss.history[:-300]

    # ----- status cards -----
    st.subheader("Live status")
    a, b, c = st.columns(3)
    a.metric("Commanded duty", f"{duty:.1f} %" if duty is not None else "--")
    b.metric("Applied on ESP32", f"{applied:.1f} %" if applied is not None else "--")
    c.metric("ESP32", device)

    d, e, f = st.columns(3)
    d.metric("Commanded frequency", f"{freq / 1000:.0f} kHz" if freq is not None else "--")
    e.metric("Applied frequency", f"{applied_freq / 1000:.0f} kHz" if applied_freq is not None else "--")
    f.metric("Firmware", fw if fw else "-- (pre-2.0)")

    g, h, i = st.columns(3)
    g.metric("Last seen", f"{age:.0f} s ago" if age is not None else "never")
    h.metric("WiFi signal", f"{s['rssi']} dBm" if s.get("rssi") is not None else "--")
    i.metric("ESP32 uptime", f"{s['uptime']} s" if s.get("uptime") is not None else "--")

    in_sync = (online and applied is not None and duty is not None and abs(applied - duty) < 0.05 and
               (applied_freq is None or freq is None or abs(applied_freq - freq) < 1))
    if in_sync:
        st.success("In sync: the ESP32 is running what you commanded.")
    elif online:
        st.info("Waiting for the ESP32 to pick up the new setting.")

    # ----- charts -----
    df = pd.DataFrame(ss.history).set_index("time")
    st.caption("Duty (%) since this page was opened")
    st.line_chart(df[["Commanded duty (%)", "Applied duty (%)"]])
    st.caption("Frequency (kHz) since this page was opened")
    st.line_chart(df[["Commanded freq (kHz)", "Applied freq (kHz)"]])

    st.caption("Event log (newest first)")
    st.code("\n".join(ss.events[:12]) or "No events yet", language=None)


with right:
    live()
