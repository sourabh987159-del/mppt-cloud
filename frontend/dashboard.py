import time
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title="MPPT Live Dashboard", layout="wide")

# "https://mppt-backend.onrender.com"
BACKEND_URL = st.secrets.get("BACKEND_URL", "http://localhost:5000")

st.title("MPPT System — Live Dashboard")
st.caption(f"Backend: {BACKEND_URL}")

refresh_seconds = st.sidebar.slider("Refresh every (seconds)", 2, 30, 5)
limit = st.sidebar.slider("Points to show", 20, 500, 100)

placeholder = st.empty()


def fetch(source: str) -> pd.DataFrame:
    try:
        resp = requests.get(f"{BACKEND_URL}/data", params={"source": source, "limit": limit}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.sidebar.error(f"Could not reach backend: {e}")
        return pd.DataFrame(columns=["timestamp", "voltage", "current"])

    if not data:
        return pd.DataFrame(columns=["timestamp", "voltage", "current"])

    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


while True:
    with placeholder.container():
        col1, col2 = st.columns(2)

        pv_df = fetch("pv")
        out_df = fetch("output")

        with col1:
            st.subheader("PV-side (Sensor A)")
            if not pv_df.empty:
                st.line_chart(pv_df.set_index("timestamp")[["voltage", "current"]])
                latest = pv_df.iloc[-1]
                st.metric("Voltage", f"{latest['voltage']:.2f} V")
                st.metric("Current", f"{latest['current']:.2f} A")
            else:
                st.info("No PV-side data yet.")

        with col2:
            st.subheader("Output-side (Sensor B)")
            if not out_df.empty:
                st.line_chart(out_df.set_index("timestamp")[["voltage", "current"]])
                latest = out_df.iloc[-1]
                st.metric("Voltage", f"{latest['voltage']:.2f} V")
                st.metric("Current", f"{latest['current']:.2f} A")
            else:
                st.info("No output-side data yet.")

    time.sleep(refresh_seconds)
    st.rerun()
