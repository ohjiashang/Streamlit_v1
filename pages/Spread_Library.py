"""Spread Library — gallery of all diffs' EW_adj at once.

2-column grid of interactive Plotly mini-charts.
Toggle: full history vs Jan 2025+.
Visual scan for mean-reverting vs trending series.
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Spread Library", layout="wide")

PAGE_DIR = Path(__file__).resolve().parent
SPREAD_DIR = PAGE_DIR.parent / "data" / "spreads"
INDEX_FP = SPREAD_DIR / "index.json"

PG_LABEL = {"Dist": "Distillates", "Lights": "Lights",
             "FO": "Fuel Oil", "Crude": "Crude", "GTGN": "GT/GN"}
PG_ORDER = ["Crude", "Dist", "FO", "Lights", "GTGN"]
PG_COLOR = {"Crude": "#1f77b4", "Dist": "#d62728", "FO": "#2ca02c",
             "Lights": "#9467bd", "GTGN": "#ff7f0e"}


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


def build_chart(df: pd.DataFrame, diff_name: str, pg: str,
                 last_med: float | None) -> go.Figure:
    fig = go.Figure()
    # Bands
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["upper_bound"],
        line=dict(color="lightblue", width=0.6, dash="dot"),
        showlegend=False, hoverinfo="skip", name="upper",
    ))
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["lower_bound"],
        line=dict(color="lightblue", width=0.6, dash="dot"),
        fill="tonexty", fillcolor="rgba(173,216,230,0.12)",
        showlegend=False, hoverinfo="skip", name="lower",
    ))
    # Median
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["rolling_median"],
        line=dict(color="grey", width=0.9),
        showlegend=False, name="median",
    ))
    # Spread
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["EW_adj"],
        line=dict(color="black", width=1.2),
        showlegend=False, name="EW_adj",
        hovertemplate="%{x|%Y-%m-%d}: %{y:.3f}<extra></extra>",
    ))
    # Current marker
    last = df.iloc[-1]
    fig.add_trace(go.Scatter(
        x=[last["Date"]], y=[last["EW_adj"]],
        mode="markers",
        marker=dict(symbol="diamond", size=9, color="orange",
                     line=dict(width=1, color="black")),
        showlegend=False, hoverinfo="skip",
    ))
    pg_color = PG_COLOR.get(pg, "#333")
    fig.update_layout(
        height=240,
        margin=dict(t=30, b=20, l=8, r=8),
        title=dict(
            text=f"<b><span style='color:{pg_color}'>{pg}</span></b> · {diff_name}  "
                  f"<span style='color:gray;font-size:11px'>last={last['EW_adj']:.2f}</span>",
            font=dict(size=12),
            x=0.02, xanchor="left",
        ),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        hovermode="x unified",
        plot_bgcolor="white",
    )
    return fig


# ── Header ───────────────────────────────────────────────────────
st.title("Spread Library")
st.caption(
    "Gallery of all 38 diffs · 1mbox shape · Y2026 classifier-recommended cell. "
    "Use this to scan visually for mean-reverting vs trending series."
)

# ── Load index ───────────────────────────────────────────────────
index = load_index()
if not index:
    st.error(f"No data found. Expected: {INDEX_FP}")
    st.stop()

# ── Sidebar: view toggle only ────────────────────────────────────
st.sidebar.header("View")
view = st.sidebar.radio(
    "Date range",
    options=["Full history", "Jan 2025 onwards"],
    index=0,
)
st.sidebar.divider()

# Filter index by product group (optional)
pg_filter = st.sidebar.multiselect(
    "Filter by family (optional)",
    options=PG_ORDER,
    default=PG_ORDER,
    format_func=lambda g: PG_LABEL.get(g, g),
)
st.sidebar.caption(f"{len(index)} diffs total.")

# Sort entries: group by product_group, then by diff
def sort_key(e):
    pg_idx = PG_ORDER.index(e["product_group"]) if e["product_group"] in PG_ORDER else 99
    return (pg_idx, e["diff"])

entries = [e for e in index if e["product_group"] in pg_filter]
entries = sorted(entries, key=sort_key)

# ── Quick scan strip ─────────────────────────────────────────────
n1, n2, n3, n4 = st.columns(4)
with n1:
    st.metric("Diffs shown", len(entries))
with n2:
    st.metric("Range", view)
with n3:
    last_bars = sorted({e["last_bar"] for e in entries})
    st.metric("Latest bar", last_bars[-1] if last_bars else "n/a")
with n4:
    st.metric("Source",
               "Universe Y2026 top-1 / 1mbox")

st.divider()

# ── 2-column grid ────────────────────────────────────────────────
for i in range(0, len(entries), 2):
    col1, col2 = st.columns(2, gap="small")
    for col, e in zip([col1, col2], entries[i:i + 2]):
        with col:
            df = load_spread(e["data_file"])
            if view == "Jan 2025 onwards":
                df = df[df["Date"] >= pd.Timestamp("2025-01-01")].reset_index(drop=True)
            if df.empty:
                st.caption(f"{e['diff']}: no data in selected range")
                continue
            fig = build_chart(df, e["diff"], e["product_group"], e.get("last_med"))
            st.plotly_chart(fig, use_container_width=True,
                              config={"displayModeBar": False})

st.divider()
st.caption(
    "All charts read precomputed parquets under `data/spreads/`. "
    "Generated via `analytics/_generate_spread_library.py`."
)
