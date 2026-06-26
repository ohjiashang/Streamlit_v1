"""Spread Library — 9/10-year EW_adj chart for every diff in the universe.

Reads precomputed parquets from data/spreads/<safe_diff>.parquet.
Interactive Plotly chart matching the Mean Reversion drilldown style.
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Spread Library", layout="wide")

PAGE_DIR = Path(__file__).resolve().parent
SPREAD_DIR = PAGE_DIR.parent / "data" / "spreads"
INDEX_FP = SPREAD_DIR / "index.json"

PG_LABEL = {"Dist": "Distillates", "Lights": "Lights",
             "FO": "Fuel Oil", "Crude": "Crude", "GTGN": "GT/GN"}


@st.cache_data(ttl=900)
def load_index() -> list[dict]:
    if not INDEX_FP.exists():
        return []
    return json.loads(INDEX_FP.read_text())


@st.cache_data(ttl=900)
def load_spread(filename: str) -> pd.DataFrame:
    fp = SPREAD_DIR / filename
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


# ── Header ───────────────────────────────────────────────────────
st.title("Spread Library")
st.caption("Per-diff EW_adj history with rolling median + entry bands. "
            "Top-1 cell of each diff (1mbox shape, Y2026 classifier).")

# ── Load index ───────────────────────────────────────────────────
index = load_index()
if not index:
    st.error(f"No data found. Expected: {INDEX_FP}")
    st.info("Run `analytics/_generate_spread_library.py` to produce data, "
             "then commit & push `data/spreads/`.")
    st.stop()

# ── Sidebar: family + diff + view ────────────────────────────────
st.sidebar.header("Filters")

groups_present = sorted({e["product_group"] for e in index})
fam_choice = st.sidebar.selectbox(
    "Product family",
    options=groups_present,
    format_func=lambda g: f"{g} — {PG_LABEL.get(g, g)}",
    index=0,
)

diffs_in_family = sorted({e["diff"] for e in index
                            if e["product_group"] == fam_choice})
diff_choice = st.sidebar.selectbox("Diff", options=diffs_in_family, index=0)

view = st.sidebar.radio(
    "Date range",
    options=["Full history", "Jan 2025 onwards"],
    index=0,
    help="Toggle between the full 9-year view and a recent zoom. "
          "You can also pan/zoom the chart freely.",
)

st.sidebar.divider()

# Find entry
entry = next((e for e in index
              if e["product_group"] == fam_choice
              and e["diff"] == diff_choice), None)

if entry is None:
    st.warning("No matching data for selection.")
    st.stop()

# ── Top strip: meta info ─────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("Family", PG_LABEL.get(fam_choice, fam_choice))
with m2:
    st.metric("Diff", diff_choice)
with m3:
    st.metric("Last bar", entry["last_bar"])
with m4:
    st.metric("Last EW_adj", f"{entry['last_ew_adj']:.3f}")
with m5:
    if entry.get("last_med") is not None:
        st.metric("Last median", f"{entry['last_med']:.3f}")

st.caption(
    f"**Cell:** `{entry['cell']}`  ·  "
    f"**W:** {entry['W']}m  ·  "
    f"**SE:** {entry['SE']}σ  ·  "
    f"**SL:** {entry['SL']}σ  ·  "
    f"**Data:** {entry['first_bar']} → {entry['last_bar']}"
)

# ── Chart (Plotly, drilldown style) ──────────────────────────────
df = load_spread(entry["data_file"])
if view == "Jan 2025 onwards":
    df = df[df["Date"] >= pd.Timestamp("2025-01-01")].reset_index(drop=True)

fig = make_subplots(rows=1, cols=1)

# Upper / lower bands with light-blue fill (same as drilldown)
fig.add_trace(go.Scatter(
    x=df["Date"], y=df["upper_bound"],
    name=f"upper (med + {entry['SE']}σ)",
    line=dict(color="lightblue", width=0.8, dash="dot"),
))
fig.add_trace(go.Scatter(
    x=df["Date"], y=df["lower_bound"],
    name=f"lower (med − {entry['SE']}σ)",
    line=dict(color="lightblue", width=0.8, dash="dot"),
    fill="tonexty", fillcolor="rgba(173,216,230,0.15)",
))
# Rolling median
fig.add_trace(go.Scatter(
    x=df["Date"], y=df["rolling_median"],
    name=f"median ({entry['W']}m)",
    line=dict(color="grey", width=1.0),
))
# Spread normalised (main line — same colour/width as drilldown)
fig.add_trace(go.Scatter(
    x=df["Date"], y=df["EW_adj"],
    name="spread_normalised",
    line=dict(color="black", width=1.2),
))
# Current marker
last = df.iloc[-1]
fig.add_trace(go.Scatter(
    x=[last["Date"]], y=[last["EW_adj"]],
    mode="markers",
    name=f"current ({last['EW_adj']:.3f})",
    marker=dict(symbol="diamond", size=14, color="orange",
                line=dict(width=1.5, color="black")),
))

fig.update_layout(
    height=560,
    margin=dict(t=40, b=20, l=10, r=10),
    legend=dict(orientation="h", yanchor="top", y=-0.05),
    title=dict(
        text=f"{diff_choice} 1mbox · {entry['fname']} "
              f"W{entry['W']}M_SE{entry['SE']}_SL{entry['SL']}",
        font=dict(size=14),
    ),
    hovermode="x unified",
)
fig.update_xaxes(title_text="Date")
fig.update_yaxes(title_text="spread_normalised")
st.plotly_chart(fig, use_container_width=True)

# ── Distribution stats ───────────────────────────────────────────
st.subheader("Distribution & extremes (current view)")
if not df.empty:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Mean", f"{df['EW_adj'].mean():.3f}")
    with c2:
        st.metric("Std", f"{df['EW_adj'].std():.3f}")
    with c3:
        st.metric("Max", f"{df['EW_adj'].max():.3f}")
    with c4:
        st.metric("Min", f"{df['EW_adj'].min():.3f}")

st.divider()
st.caption(f"Data: `data/spreads/{entry['data_file']}` "
            f"(precomputed via `analytics/_generate_spread_library.py`)")
