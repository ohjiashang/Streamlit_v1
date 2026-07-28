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
        # Semi-transparent grey reads well in BOTH light and dark themes
        # (darkens a light bg, lightens a dark bg); text colour left to the theme.
        return ["font-weight:bold;background-color:rgba(128,128,128,0.25)" if hit else "" for _ in row]

    styled = (df.style
                .apply(_bold_total, axis=1)
                .set_properties(**{"text-align": "right"})
                .format("{:,}"))

    # Thick grey rules: under the totals row, and wrapping the FLAT row
    # (span the label + data cells).
    grey = "3px solid #888"
    styles = [{"selector": "tbody tr:nth-child(1) td, tbody tr:nth-child(1) th",
               "props": [("border-bottom", grey)]}]
    if "FLAT" in t["bin_labels"]:
        pos = 2 + t["bin_labels"].index("FLAT")   # tbody nth-child (row 1 = totals)
        styles.append({"selector": f"tbody tr:nth-child({pos}) td, tbody tr:nth-child({pos}) th",
                       "props": [("border-top", grey), ("border-bottom", grey)]})
    styled = styled.set_table_styles(styles, overwrite=False)
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

    # Status banner (app.py style): last-updated time + how long ago.
    age_txt = f"  ·  **{age}s ago**" if age is not None else ""
    st.success(f"**Last updated:** {updated} SGT{age_txt}  ·  ↻ auto-refresh every {REFRESH_SEC}s")

    tables = {t["title"]: t for t in data.get("tables", [])}

    # 2x2 grid: Dubai | S92  on top, SGO | SKO below.
    for left, right in [("Dubai", "S92"), ("SGO", "SKO")]:
        cols = st.columns(2)
        for col, name in zip(cols, (left, right)):
            if name in tables:
                with col:
                    render_table(tables[name])


live()
