import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="MPPT Live Dashboard", layout="wide")

BACKEND_URL = st.secrets.get("BACKEND_URL", "http://localhost:5000")

st.title("MPPT System — Live Dashboard")
st.caption(f"Backend: {BACKEND_URL}")

refresh_seconds = st.sidebar.slider("Refresh every (seconds)", 2, 30, 5)
limit = st.sidebar.slider("Points to show", 20, 500, 100)
current_junction = st.sidebar.selectbox(
    "Which junction is the probe on right now?",
    ["J1 (~2.475 V expected)", "J2 (~1.65 V expected)", "J3 (~0.825 V expected)"],
)

placeholder = st.empty()


def fetch(source: str) -> pd.DataFrame:
    try:
        resp = requests.get(f"{BACKEND_URL}/data", params={"source": source, "limit": limit}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.sidebar.error(f"Could not reach backend: {e}")
        return pd.DataFrame(columns=["timestamp", "voltage"])

    if not data:
        return pd.DataFrame(columns=["timestamp", "voltage"])

    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


while True:
    with placeholder.container():
        st.subheader(f"Live probe reading — labeled as {current_junction}")

        df = fetch("demo")
        if not df.empty:
            st.line_chart(df.set_index("timestamp")[["voltage"]])
            latest = df.iloc[-1]
            st.metric("Voltage", f"{latest['voltage']:.3f} V")
        else:
            st.info("No probe data yet.")

    time.sleep(refresh_seconds)
    st.rerun()
