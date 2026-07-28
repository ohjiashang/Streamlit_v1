"""TAPS page — live T&S bin tallies (Dubai / SGO / SKO).

Reads the JSON the DubaiTS daemon uploads to Firebase Storage every cycle
(taps/display.json, written with Cache-Control: no-cache so reads are fresh) and
auto-refreshes. Works anywhere — no credentials needed, the object is public-read.
"""
import json
import time
import urllib.request
import urllib.parse

import pandas as pd
import streamlit as st

st.set_page_config(page_title="TAPS", layout="wide")

FIREBASE_BUCKET = "hotei-streamlit.firebasestorage.app"
REMOTE_PATH = "taps/display.json"


def _public_url() -> str:
    p = urllib.parse.quote(REMOTE_PATH, safe="")
    return f"https://firebasestorage.googleapis.com/v0/b/{FIREBASE_BUCKET}/o/{p}?alt=media"


def fetch():
    # cache-bust so a proxy can never hand us a stale copy
    url = _public_url() + f"&_={int(time.time())}"
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def render_table(t: dict) -> None:
    index = [t["total_label"]] + t["bin_labels"]
    matrix = [t["totals"]] + [t["bins"][bl] for bl in t["bin_labels"]]
    df = pd.DataFrame(matrix, index=index, columns=t["columns"])

    def _bold_total(row):
        hit = row.name == t["total_label"]
        return ["font-weight:bold;background-color:#eef2ff" if hit else "" for _ in row]

    styled = (df.style
                .apply(_bold_total, axis=1)
                .set_properties(**{"text-align": "right"})
                .format("{:,}"))
    st.markdown(f"### {t['title']}")
    st.table(styled)


st.title("TAPS")

refresh_sec = st.sidebar.slider("Auto-refresh (seconds)", 5, 60, 10, 5)
st.sidebar.caption("Lag ≈ daemon poll (15–30s) + this refresh. Data via Firebase (no-cache).")


@st.fragment(run_every=f"{refresh_sec}s")
def live():
    try:
        data = fetch()
    except Exception as e:
        st.error(f"Could not load data from Firebase: {e}")
        return

    updated = data.get("updated", "?")
    age = None
    if data.get("updated_epoch"):
        age = max(0, int(time.time() - float(data["updated_epoch"])))

    left, right = st.columns([4, 1])
    with left:
        age_txt = f"  ·  {age}s ago" if age is not None else ""
        st.caption(f"**Last updated:** {updated} SGT{age_txt}")
    with right:
        st.caption(f"↻ every {refresh_sec}s")
    if age is not None and age > 180:
        st.warning(f"⚠️ Data is {age}s old — daemon may be paused/stopped, or market is closed.")

    tables = data.get("tables", [])
    for col, t in zip(st.columns(len(tables)), tables):
        with col:
            render_table(t)


live()
