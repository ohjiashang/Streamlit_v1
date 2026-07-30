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
PAGE_POLL_SEC = 5   # page Firebase-read rate DURING the daemon's fast (10s ICE) window (NO ICE).
                    # Outside it, the page reads at the daemon's own cadence (30s) — no point
                    # polling faster than the data changes. Cuts lag at zero ICE cost.
STALE_AFTER_SEC = 120   # if the feed hasn't updated in this long (daemon stopped @17:00 / stalled),
                        # show a neutral grey "as of HH:MM" bar instead of the live green one.
# Highlight the premium (+XC) or discount (-XC) group when that group's summed value
# (across all its rows and contracts) reaches the table's threshold. FLAT + totals never
# highlight. Live/conditional — resets at 07:00 or when the sum drops back below.
HIGHLIGHT_THRESHOLDS = {
    "Dubai": 1000,
    "SGO": 500, "SKO": 500, "S92": 500,
    "S0.5": 500 / 6.35, "S380": 500 / 6.35,
}
HIGHLIGHT_DEFAULT = 500


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

    # Premium (+XC) / discount (-XC) groups — FLAT and the totals row are excluded.
    # Highlight the WHOLE group when its summed value (all its rows, all contracts)
    # reaches the table's threshold.
    def _grp_sum(prefix):
        return sum(float(v) for bl in t["bin_labels"] if bl.startswith(prefix)
                   for v in t["bins"][bl])
    thr = HIGHLIGHT_THRESHOLDS.get(t["title"], HIGHLIGHT_DEFAULT)
    prem_hot = _grp_sum("+") >= thr
    disc_hot = _grp_sum("-") >= thr

    def _cell_style(row):
        name = str(row.name)
        if name == t["total_label"]:   # totals row: grey emphasis (both themes)
            return ["font-weight:bold;background-color:rgba(128,128,128,0.25)"] * len(row)
        if (name.startswith("+") and prem_hot) or (name.startswith("-") and disc_hot):
            return ["font-weight:bold;background-color:rgba(255,165,0,0.55)"] * len(row)
        return [""] * len(row)         # FLAT and un-triggered groups: no highlight

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

# Page read rate: fast (PAGE_POLL_SEC) during the daemon's 10s window to cut lag, else match
# the daemon's cadence (reading faster than the data changes is wasted). Reading the JSON
# touches NO ICE. Re-tune via a full rerun when the daemon's cadence changes.
def _page_poll(di):
    return PAGE_POLL_SEC if di <= 10 else di

if "page_poll" not in st.session_state:
    try:
        st.session_state.page_poll = _page_poll(int(fetch().get("interval", REFRESH_SEC)))
    except Exception:
        st.session_state.page_poll = REFRESH_SEC


@st.fragment(run_every=f"{st.session_state.page_poll}s")
def live():
    try:
        data = fetch()
    except Exception as e:
        st.error(f"Could not load data from Firebase: {e}")
        return

    updated = data.get("updated", "?")
    di = int(data.get("interval", REFRESH_SEC))     # daemon's data-update cadence
    want = _page_poll(di)
    if want != st.session_state.page_poll:          # cadence changed -> re-tune page rate
        st.session_state.page_poll = want
        try:
            st.rerun(scope="app")
        except TypeError:
            st.rerun()

    age = None
    if data.get("updated_epoch"):
        age = max(0, int(time.time() - float(data["updated_epoch"])))

    # Live GREEN bar when fresh; neutral GREY "as of <ts>" bar when the daemon is stopped or
    # stalled (after 17:00, overnight, or a mid-day hang) — no scary warning, just marks the
    # data as static. Grey rgba reads in both light/dark themes.
    if age is None or age > STALE_AFTER_SEC:
        st.markdown(
            f'<div style="background:rgba(128,128,128,0.2);padding:0.5rem 0.9rem;'
            f'border-radius:0.5rem;">As of {updated} SGT</div>',
            unsafe_allow_html=True)
    else:
        st.success(f"**Last updated:** {updated} SGT  ·  **{age}s ago**  ·  ↻ updates every {di}s")

    tables = {t["title"]: t for t in data.get("tables", [])}

    # grid: Dubai | Brent SMM, S92 | SGO, SKO | S0.5, S380 | LSGO SMM.
    for left, right in [("Dubai", "Brent SMM"), ("S92", "SGO"),
                        ("SKO", "S0.5"), ("S380", "LSGO SMM")]:
        cols = st.columns(2)
        for col, name in zip(cols, (left, right)):
            if name in tables:
                with col:
                    render_table(tables[name])


live()
