"""TAPS page — live T&S bin tallies (Dubai / SGO / SKO).

Reads taps/display.json from Firebase Storage (uploaded by the DubaiTS daemon each
cycle, Cache-Control: no-cache) and auto-refreshes every 30s. Public-read, no creds.

Layout: Dubai on row 1, SGO + SKO on row 2; each table is 1/4 of the page width.
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
REFRESH_SEC = 30


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
    st.markdown(f"#### {t['title']}")
    st.table(styled)


st.title("TAPS")


@st.fragment(run_every=f"{REFRESH_SEC}s")
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

    # Prominent status banner (app.py style): green when fresh, amber when stale.
    age_txt = f"  ·  **{age}s ago**" if age is not None else ""
    banner = f"**Last updated:** {updated} SGT{age_txt}  ·  ↻ auto-refresh every {REFRESH_SEC}s"
    if age is not None and age > 180:
        st.warning(banner + "  ·  ⚠️ Data is stale — daemon may be paused/stopped, or market closed.")
    else:
        st.success(banner)

    tables = {t["title"]: t for t in data.get("tables", [])}

    # Row 1: Dubai — 1/4 page width (first of four columns).
    row1 = st.columns(4)
    if "Dubai" in tables:
        with row1[0]:
            render_table(tables["Dubai"])

    # Row 2: SGO + SKO — each 1/4 page width.
    row2 = st.columns(4)
    for i, name in enumerate(["SGO", "SKO"]):
        if name in tables:
            with row2[i]:
                render_table(tables[name])


live()
