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
def load_spread(filename: str, W: int, SE: float) -> pd.DataFrame:
    fp = SPREAD_DIR / filename
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    # Compute rolling median + bands if not already present
    if "rolling_median" not in df.columns:
        # ~22 trading days per month
        win = max(int(W * 22), 5)
        df["rolling_median"] = df["EW_adj"].rolling(win, min_periods=win).median()
        df["rolling_std"] = df["EW_adj"].rolling(win, min_periods=win).std()
        df["upper_bound"] = df["rolling_median"] + SE * df["rolling_std"]
        df["lower_bound"] = df["rolling_median"] - SE * df["rolling_std"]
    return df


def build_chart(df: pd.DataFrame, diff_name: str, pg: str,
                 shape: str, last_med: float | None) -> go.Figure:
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
            text=f"<b><span style='color:{pg_color}'>{pg}</span></b> · {diff_name} "
                  f"<span style='color:gray;font-size:10px'>({shape})</span> "
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
    "Gallery of all 38 diffs · classifier-recommended top-1 cell per diff (Y2026 OOS, "
    "best across outright/1mbox/3mbox). Use this to scan visually for mean-reverting "
    "vs trending series."
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
    st.metric("Source", "Y2026 top-1 (all shapes)")

st.divider()

# ── 2-column grid ────────────────────────────────────────────────
for i in range(0, len(entries), 2):
    col1, col2 = st.columns(2, gap="small")
    for col, e in zip([col1, col2], entries[i:i + 2]):
        with col:
            df = load_spread(e["data_file"], e["W"], e["SE"])
            if view == "Jan 2025 onwards":
                df = df[df["Date"] >= pd.Timestamp("2025-01-01")].reset_index(drop=True)
            if df.empty:
                st.caption(f"{e['diff']}: no data in selected range")
                continue
            fig = build_chart(df, e["diff"], e["product_group"],
                                e.get("shape", ""), e.get("last_med"))
            st.plotly_chart(fig, use_container_width=True,
                              config={"displayModeBar": False})

st.divider()

# ── Custom diff combiner (Path A MVP) ─────────────────────────────
st.header("Custom diff combiner")
st.caption(
    "Quick exploratory tool: combine 2 of the 38 precomputed diffs with `+` or `−`. "
    "Useful for synthetic cross-product spreads (e.g. `S380-Brt − GO_EW`). "
    "For arbitrary per-leg per-offset formulas (full `SYS[3] - SGO[2] + ICEGO[3]` style), "
    "I'll wire up the full formula engine next."
)

all_diff_choices = sorted(
    [(e["product_group"], e["diff"], e["data_file"],
       e.get("W", 12), e.get("SE", 2.0), e.get("shape", ""))
      for e in index],
    key=sort_key,
)
diff_options = [f"{pg} · {df} ({sh})" for pg, df, _, _, _, sh in all_diff_choices]

cc1, cc2, cc3, cc4 = st.columns([3, 1, 3, 1])
with cc1:
    leg1_idx = st.selectbox("Leg 1", options=range(len(diff_options)),
                              format_func=lambda i: diff_options[i],
                              key="leg1_idx")
with cc2:
    op = st.selectbox("Op", options=["+", "−"], index=1, key="combine_op")
with cc3:
    default_l2 = min(leg1_idx + 1, len(diff_options) - 1)
    leg2_idx = st.selectbox("Leg 2", options=range(len(diff_options)),
                              format_func=lambda i: diff_options[i],
                              index=default_l2, key="leg2_idx")
with cc4:
    rolling_W_combo = st.number_input("W (m)", min_value=3, max_value=24,
                                          value=12, step=1,
                                          key="combine_W")

leg1 = all_diff_choices[leg1_idx]
leg2 = all_diff_choices[leg2_idx]

df1 = load_spread(leg1[2], leg1[3], leg1[4])
df2 = load_spread(leg2[2], leg2[3], leg2[4])

# Align on date and compute combined series
merged = (df1[["Date", "EW_adj"]].rename(columns={"EW_adj": "leg1"})
                                  .merge(df2[["Date", "EW_adj"]].rename(
                                                columns={"EW_adj": "leg2"}),
                                          on="Date", how="inner"))
if merged.empty:
    st.warning("No overlapping dates for the chosen legs.")
else:
    sign = 1 if op == "+" else -1
    merged["EW_adj"] = merged["leg1"] + sign * merged["leg2"]
    # Recompute rolling median + bands on the combined series
    win = max(int(rolling_W_combo * 22), 5)
    merged["rolling_median"] = merged["EW_adj"].rolling(win, min_periods=win).median()
    merged["rolling_std"] = merged["EW_adj"].rolling(win, min_periods=win).std()
    merged["upper_bound"] = merged["rolling_median"] + 2.0 * merged["rolling_std"]
    merged["lower_bound"] = merged["rolling_median"] - 2.0 * merged["rolling_std"]
    if view == "Jan 2025 onwards":
        merged = merged[merged["Date"] >= pd.Timestamp("2025-01-01")].reset_index(drop=True)

    diff_label = f"{leg1[1]} {op} {leg2[1]}"
    pg_label = f"{leg1[0]} / {leg2[0]}"
    last_row = merged.iloc[-1]
    cmb_metrics_c1, cmb_metrics_c2, cmb_metrics_c3, cmb_metrics_c4 = st.columns(4)
    with cmb_metrics_c1:
        st.metric("Last EW_adj (combined)", f"{last_row['EW_adj']:.3f}")
    with cmb_metrics_c2:
        st.metric("Last median", f"{last_row['rolling_median']:.3f}"
                  if pd.notna(last_row["rolling_median"]) else "n/a")
    with cmb_metrics_c3:
        st.metric("Std (current view)", f"{merged['EW_adj'].std():.3f}")
    with cmb_metrics_c4:
        st.metric("Last bar", str(last_row["Date"].date()))

    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(
        x=merged["Date"], y=merged["upper_bound"],
        line=dict(color="lightblue", width=0.8, dash="dot"),
        showlegend=False, hoverinfo="skip", name="upper",
    ))
    fig_c.add_trace(go.Scatter(
        x=merged["Date"], y=merged["lower_bound"],
        line=dict(color="lightblue", width=0.8, dash="dot"),
        fill="tonexty", fillcolor="rgba(173,216,230,0.12)",
        showlegend=False, hoverinfo="skip", name="lower",
    ))
    fig_c.add_trace(go.Scatter(
        x=merged["Date"], y=merged["rolling_median"],
        line=dict(color="grey", width=1.0),
        name=f"median ({rolling_W_combo}m)",
    ))
    fig_c.add_trace(go.Scatter(
        x=merged["Date"], y=merged["EW_adj"],
        line=dict(color="black", width=1.3),
        name=diff_label,
        hovertemplate="%{x|%Y-%m-%d}: %{y:.3f}<extra></extra>",
    ))
    fig_c.add_trace(go.Scatter(
        x=[last_row["Date"]], y=[last_row["EW_adj"]],
        mode="markers",
        marker=dict(symbol="diamond", size=12, color="orange",
                     line=dict(width=1, color="black")),
        showlegend=False, hoverinfo="skip",
    ))
    fig_c.update_layout(
        height=420,
        margin=dict(t=40, b=20, l=10, r=10),
        title=dict(text=f"<b>{pg_label}</b> · {diff_label}",
                    font=dict(size=13)),
        legend=dict(orientation="h", yanchor="top", y=-0.1),
        plot_bgcolor="white",
        hovermode="x unified",
    )
    fig_c.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig_c.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    st.plotly_chart(fig_c, use_container_width=True)

    st.caption(
        f"Combined formula: `{diff_label}` (computed by date-aligned arithmetic on the "
        f"EW_adj of leg-1 and leg-2). Rolling window for median+bands is "
        f"configurable above (`W={rolling_W_combo}m`)."
    )

st.divider()
st.caption(
    "All charts read precomputed parquets under `data/spreads/`. "
    "Generated via `analytics/_generate_spread_library.py`."
)
