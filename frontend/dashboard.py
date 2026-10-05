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

JUNCTIONS = ["j1", "j2", "j3"]


def fetch(source: str) -> pd.DataFrame:
    try:
        resp = requests.get(f"{BACKEND_URL}/data", params={"source": source, "limit": limit}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.sidebar.error(f"Could not reach backend ({source}): {e}")
        return pd.DataFrame(columns=["timestamp", "voltage"])

    if not data:
        return pd.DataFrame(columns=["timestamp", "voltage"])

    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


while True:
    with placeholder.container():
        cols = st.columns(3)

        for col, source in zip(cols, JUNCTIONS):
            df = fetch(source)
            with col:
                st.subheader(source.upper())
                if not df.empty:
                    st.line_chart(df.set_index("timestamp")[["voltage"]])
                    latest = df.iloc[-1]
                    st.metric("Voltage", f"{latest['voltage']:.3f} V")
                else:
                    st.info(f"No {source.upper()} data yet.")

    time.sleep(refresh_seconds)
    st.rerun()
