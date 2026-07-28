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
HIGHLIGHT_THRESHOLD = 5000   # highlight non-total cells whose live value >= this


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

    def _cell_style(row):
        # Total row: semi-transparent grey (reads in both light/dark themes).
        # Non-total cells >= threshold: semi-transparent AMBER (distinct from grey).
        # Both are live/conditional — no state; at 07:00 reset or a drop below the
        # threshold the value changes and the highlight simply goes away.
        is_total = row.name == t["total_label"]
        out = []
        for v in row:
            if is_total:
                out.append("font-weight:bold;background-color:rgba(128,128,128,0.25)")
                continue
            try:
                hot = float(v) >= HIGHLIGHT_THRESHOLD
            except (ValueError, TypeError):
                hot = False
            out.append("font-weight:bold;background-color:rgba(255,165,0,0.55)" if hot else "")
        return out

    def _fmt(v):
        # whole numbers as ints (0, 112); composite fractions to 1 dp (32.7)
        f = float(v)
        return f"{int(f):,}" if f == int(f) else f"{f:,.1f}"

    styled = (df.style
                .apply(_cell_style, axis=1)
                .set_properties(**{"text-align": "right"})
                .format(_fmt))

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

    # grid: Dubai | S92, SGO | SKO, S0.5 | S380 (S380 shows once added).
    for left, right in [("Dubai", "S92"), ("SGO", "SKO"), ("S0.5", "S380")]:
        cols = st.columns(2)
        for col, name in zip(cols, (left, right)):
            if name in tables:
                with col:
                    render_table(tables[name])


live()
