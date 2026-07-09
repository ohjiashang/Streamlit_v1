"""SHADOW methodology page — mirrors the main Mean Reversion page layout."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="MR — Entry-VaR Shadow", layout="wide")

ROOT = Path(__file__).resolve().parents[1] / "data" / "entry_var_shadow"
PICKS_DIR = ROOT / "picks"


@st.cache_data(ttl=3600)
def load_parquet(name: str) -> pd.DataFrame:
    fp = ROOT / f"{name}.parquet"
    return pd.read_parquet(fp) if fp.exists() else pd.DataFrame()


@st.cache_data(ttl=3600)
def load_pick_df(cell: str) -> pd.DataFrame:
    safe = cell.replace("/", "_")
    fp = PICKS_DIR / f"{safe}__df.parquet"
    if not fp.exists():
        return pd.DataFrame()
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


@st.cache_data(ttl=3600)
def load_pick_trades(cell: str) -> pd.DataFrame:
    safe = cell.replace("/", "_")
    fp = PICKS_DIR / f"{safe}__trades.parquet"
    if not fp.exists():
        return pd.DataFrame()
    t = pd.read_parquet(fp)
    if not t.empty:
        t["entry_date"] = pd.to_datetime(t["entry_date"])
        t["exit_date"] = pd.to_datetime(t["exit_date"])
    return t


# ── Data ───────────────────────────────────────────────
shadow_w = load_parquet("shadow_weights")
shadow_m = load_parquet("shadow_metrics")
shadow_d = load_parquet("shadow_daily_pnl")
prod_m = load_parquet("prod_metrics")
prod_d = load_parquet("prod_daily_pnl")

if shadow_w.empty:
    st.error("Shadow data not bundled. Run analytics/_apply_mpt_entry_var_shadow.py first.")
    st.stop()

shadow_d["Date"] = pd.to_datetime(shadow_d["Date"])
shadow_d = shadow_d.sort_values("Date").reset_index(drop=True)
prod_d["Date"] = pd.to_datetime(prod_d["Date"])
prod_d = prod_d.sort_values("Date").reset_index(drop=True)
shad_pnl_col = "daily_pnl" if "daily_pnl" in shadow_d.columns else "portfolio_daily_pnl"
prod_pnl_col = "portfolio_daily_pnl" if "portfolio_daily_pnl" in prod_d.columns else "daily_pnl"


# ── Header (mirrors main page) ────────────────────────
col_hdr_l, col_hdr_r = st.columns([3, 1])
years = sorted(shadow_w["Year"].unique())
last_bar = shadow_d["Date"].max()
first_bar = shadow_d["Date"].min()

with col_hdr_l:
    st.title("Mean Reversion — Shadow (Entry-VaR $-MPT)")
    st.info(
        f"**Backtest window:** {first_bar.date()} → {last_bar.date()}  ·  "
        f"**{len(years)} OOS years**  ·  "
        f"Diagnostic — production **NOT** touched"
    )
    st.caption(
        "$-MPT re-solves each year's optimizer on entry-VaR-scaled dollar P&L (basis $1 unit capital). "
        "Includes IP diffs in the candidate universe. See methodology at the bottom."
    )
with col_hdr_r:
    YEAR = st.selectbox("Year", years, index=len(years) - 1)
    total_pnl_year = shadow_m[shadow_m['label'] == f'Y{YEAR}']['total_pnl'].iloc[0]
    st.metric(f"Y{YEAR} P&L", f"${total_pnl_year:+.3f}")


# ── Section A: Scorecards (mirrors main page 7-column layout) ─
YEAR = int(YEAR)
y_row = shadow_m[shadow_m["label"] == f"Y{YEAR}"].iloc[0]
prod_y = prod_m[prod_m["label"] == f"Y{YEAR}"]
prod_y_row = prod_y.iloc[0] if not prod_y.empty else None

picks = shadow_w[shadow_w["Year"] == YEAR].sort_values("weight", ascending=False).reset_index(drop=True)

c1, c2, c3, c4, c5, c6, c7, _ = st.columns([1, 1, 1, 1, 1, 1, 1, 2])
with c1:
    delta = None
    if prod_y_row is not None:
        d = y_row["total_pnl"] - prod_y_row["total_pnl"]
        delta = f"{d:+.3f} vs prod"
    st.metric("Total P&L", f"${y_row['total_pnl']:+.3f}", delta=delta)
with c2:
    st.metric("Sharpe", f"{y_row['sharpe']:.2f}",
              delta=f"{y_row['sharpe'] - prod_y_row['sharpe']:+.2f} vs prod"
                    if prod_y_row is not None else None)
with c3:
    st.metric("Sortino", f"{y_row['sortino']:.2f}")
with c4:
    st.metric("Calmar",
              f"{y_row['calmar']:.2f}" if not pd.isna(y_row.get('calmar', np.nan)) else "—")
with c5:
    st.metric("N picks", str(len(picks)))
with c6:
    st.metric("Max DD", f"${y_row['max_drawdown']:+.3f}")
with c7:
    st.metric("Win-day %", f"{y_row['win_day_pct']:.1f}%")

st.divider()


# ── Section B: Portfolio status grid ───────────────────
st.subheader(f"Portfolio picks — Y{YEAR}")

# Compute per-pick backtest metrics: last EW_adj value in Y, last median in Y,
# trades count in Y, cell realized P&L in Y (per-bbl), status text.
import re
CELL_RE = re.compile(r"^(.+?)_W(\d+)M_SE([\d.]+)_SL([\d.]+)_SLP(\d+)$")

def cell_display_row(pick: pd.Series):
    cell = pick["cell"]
    m = CELL_RE.match(cell)
    fname = W = SE = SL = None
    if m:
        fname, W, SE, SL, _ = m.groups()
    df = load_pick_df(cell)
    trades = load_pick_trades(cell)
    trades_y = pd.DataFrame()
    if not trades.empty:
        trades_y = trades[trades["entry_date"].dt.year == YEAR]
    # Latest value in the OOS year
    if not df.empty:
        df_y = df[df["Date"].dt.year == YEAR]
        last_row = df_y.iloc[-1] if not df_y.empty else df.iloc[-1]
        current = float(last_row["EW_adj"])
        median = float(last_row["rolling_median"]) if not pd.isna(last_row["rolling_median"]) else None
    else:
        current = median = None
    # Total realized in year (per bbl)
    total_realized = float(trades_y["pnl"].sum()) if not trades_y.empty and "pnl" in trades_y.columns else 0.0
    n_trades = len(trades_y)
    n_stops = int((trades_y["exit_reason"].str.lower() == "stop").sum()) if not trades_y.empty else 0
    status = (f"{n_trades} trades, {n_stops} stops" if n_trades > 0
              else "no trades" if n_trades == 0 and not df.empty else "no data")
    return {
        "Diff": pick["diff"],
        "Shape": pick["shape"],
        "Family": pick["family"],
        "IP": "🟡" if str(pick["family"]).startswith("IP_") else "",
        "W": W, "SE": SE, "SL": SL,
        "Weight": float(pick["weight"]),
        "P_winner": float(pick.get("P_winner", np.nan)),
        "IS Sharpe": float(pick.get("sharpe", np.nan)),
        "Current": current,
        "Median": median,
        "OOS trades": status,
        "Cell realized (bbl)": total_realized,
        "Cell contrib ($)": float(pick["weight"]) * total_realized,
        "cell": cell,
    }

rows = [cell_display_row(p) for _, p in picks.iterrows()]
display_df = pd.DataFrame(rows).drop(columns=["cell"])

def _pnl_color(v):
    if pd.isna(v) or v == 0: return ""
    return "color: #27ae60" if v > 0 else "color: #c0392b"

def _highlight_ip(row):
    return ["background-color: #FFF3CD" if row.get("IP") == "🟡" else "" for _ in row]

styled = (display_df.style
          .format({
              "Weight": "{:.2%}",
              "P_winner": "{:.4f}",
              "IS Sharpe": "{:.2f}",
              "Current": "{:.3f}",
              "Median": "{:.3f}",
              "Cell realized (bbl)": "{:+.3f}",
              "Cell contrib ($)": "${:+.3f}",
          })
          .apply(_highlight_ip, axis=1)
          .map(_pnl_color, subset=["Cell realized (bbl)", "Cell contrib ($)"]))

st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Section C: Portfolio P&L (yearly-reset cumulative) ─
st.subheader(f"Portfolio P&L Y{YEAR}")
shad_series = shadow_d.set_index("Date")[shad_pnl_col]
prod_series = prod_d.set_index("Date")[prod_pnl_col]
shad_y = shad_series[shad_series.index.year == YEAR].cumsum()
prod_y_series = prod_series[prod_series.index.year == YEAR].cumsum()

col_left, col_right = st.columns([2, 1])
with col_left:
    fig_left = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                              row_heights=[0.6, 0.4],
                              subplot_titles=(f"Cumulative P&L Y{YEAR}", f"Drawdown Y{YEAR}"))
    fig_left.add_trace(go.Scatter(x=prod_y_series.index, y=prod_y_series.values,
                                    name="Production", line=dict(color="#4C72B0", width=1.6, dash="dot")),
                        row=1, col=1)
    fig_left.add_trace(go.Scatter(x=shad_y.index, y=shad_y.values,
                                    name="Shadow", line=dict(color="#D62728", width=2.2)),
                        row=1, col=1)
    fig_left.add_hline(y=0, line=dict(color="grey", width=0.5), row=1, col=1)
    dd = shad_y - shad_y.cummax()
    fig_left.add_trace(go.Scatter(x=dd.index, y=dd.values,
                                    name="Shadow DD", fill="tozeroy", line=dict(color="darkred")),
                        row=2, col=1)
    fig_left.update_layout(height=460, margin=dict(t=40, b=20, l=10, r=10),
                             legend=dict(orientation="h", yanchor="top", y=-0.10))
    fig_left.update_yaxes(title_text="Cum P&L ($)", row=1, col=1)
    fig_left.update_yaxes(title_text="DD ($)", row=2, col=1)
    st.plotly_chart(fig_left, use_container_width=True)

with col_right:
    # Per-pick contribution bars (Y-year only)
    contrib = display_df.copy().sort_values("Cell contrib ($)", ascending=True)
    fig_attr = go.Figure()
    fig_attr.add_trace(go.Bar(x=contrib["Cell contrib ($)"],
                                y=contrib["Diff"] + " (" + contrib["Shape"] + ")",
                                orientation="h",
                                marker_color=["#27ae60" if v >= 0 else "#c0392b"
                                              for v in contrib["Cell contrib ($)"]],
                                text=[f"${v:+.3f}" for v in contrib["Cell contrib ($)"]],
                                textposition="outside"))
    fig_attr.update_layout(title=f"Pick contribution Y{YEAR}",
                             height=460, margin=dict(t=40, b=20, l=10, r=10),
                             showlegend=False)
    st.plotly_chart(fig_attr, use_container_width=True)

st.divider()


# ── Section D: Drill-down per pick ─────────────────────
st.subheader("Drill-down per pick")
pick_labels = [f"{r['diff']} ({r['shape']})  ·  w={r['weight']*100:.2f}%"
                for _, r in picks.iterrows()]
selected_idx = st.selectbox("Pick", range(len(pick_labels)),
                              format_func=lambda i: pick_labels[i], key=f"drill_{YEAR}")
sel = picks.iloc[selected_idx]
df = load_pick_df(sel["cell"])
trades = load_pick_trades(sel["cell"])

if df.empty:
    st.warning(f"No bundled data for {sel['cell']}. Skipping drilldown.")
else:
    # Date range widget (default Jan year-2 → year end)
    _full_min = df["Date"].min().date()
    _full_max = df["Date"].max().date()
    _default_start = max(date(YEAR - 2, 1, 1), _full_min)
    _default_end = min(date(YEAR, 12, 31), _full_max)
    _reset_ctr_key = f"reset_ctr_{sel['cell']}"
    _reset_ctr = st.session_state.get(_reset_ctr_key, 0)
    _range_key = f"range_{sel['cell']}_{_reset_ctr}"

    col_dr_l, col_dr_r = st.columns([3, 1])
    with col_dr_l:
        rng = st.date_input("Chart date range",
                              value=(_default_start, _default_end),
                              min_value=_full_min, max_value=_full_max,
                              key=_range_key)
    with col_dr_r:
        if st.button("Reset range", key=f"reset_{sel['cell']}"):
            st.session_state[_reset_ctr_key] = _reset_ctr + 1
            st.rerun()
    if isinstance(rng, tuple) and len(rng) == 2:
        r_start, r_end = pd.Timestamp(rng[0]), pd.Timestamp(rng[1])
    else:
        r_start, r_end = pd.Timestamp(_default_start), pd.Timestamp(_default_end)

    chart_df = df[(df["Date"] >= r_start) & (df["Date"] <= r_end)]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                         row_heights=[0.7, 0.3])
    fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["EW_adj"],
                              name="EW_adj", line=dict(color="black", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["rolling_median"],
                              name="median", line=dict(color="grey", width=1.0)), row=1, col=1)
    fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["upper_bound"],
                              name="upper", line=dict(color="lightblue", width=0.8, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["lower_bound"],
                              name="lower", line=dict(color="lightblue", width=0.8, dash="dot"),
                              fill="tonexty", fillcolor="rgba(173,216,230,0.15)"), row=1, col=1)

    # Trade markers
    if not trades.empty:
        t_range = trades[(trades["entry_date"] >= r_start) & (trades["entry_date"] <= r_end)]
        longs = t_range[t_range["side"] == "long"]
        shorts = t_range[t_range["side"] == "short"]
        if not longs.empty:
            fig.add_trace(go.Scatter(x=longs["entry_date"], y=longs["entry"],
                                      mode="markers", name="long entry",
                                      marker=dict(symbol="triangle-up", size=10, color="#1f77b4")),
                            row=1, col=1)
        if not shorts.empty:
            fig.add_trace(go.Scatter(x=shorts["entry_date"], y=shorts["entry"],
                                      mode="markers", name="short entry",
                                      marker=dict(symbol="triangle-down", size=10, color="#d62728")),
                            row=1, col=1)
        stops = t_range[t_range["exit_reason"].str.lower() == "stop"]
        exits_med = t_range[t_range["exit_reason"].str.lower() != "stop"]
        if not exits_med.empty:
            fig.add_trace(go.Scatter(x=exits_med["exit_date"], y=exits_med["exit"],
                                      mode="markers", name="median exit",
                                      marker=dict(symbol="circle-open", size=8, color="black")),
                            row=1, col=1)
        if not stops.empty:
            fig.add_trace(go.Scatter(x=stops["exit_date"], y=stops["exit"],
                                      mode="markers", name="STOP exit",
                                      marker=dict(symbol="x", size=12, color="#d62728")),
                            row=1, col=1)

    # Cumulative cell P&L (in window)
    if not chart_df.empty and not trades.empty:
        # Reconstruct daily P&L per bbl inside range using EW_adj + trades
        ew = chart_df.set_index("Date")["EW_adj"]
        daily = pd.Series(0.0, index=ew.index)
        for _, tr in trades.iterrows():
            direction = 1.0 if str(tr["side"]).lower() == "long" else -1.0
            seg_start = max(tr["entry_date"], r_start)
            seg_end = min(tr["exit_date"], r_end)
            if seg_start > seg_end: continue
            seg = ew.index[(ew.index >= seg_start) & (ew.index <= seg_end)]
            for d in seg:
                if d == tr["entry_date"]:
                    daily.loc[d] += direction * (ew.loc[d] - float(tr["entry"]))
                elif d == tr["exit_date"]:
                    prev = ew.index.get_loc(d) - 1
                    if prev >= 0:
                        daily.loc[d] += direction * (float(tr["exit"]) - ew.iloc[prev])
                else:
                    prev = ew.index.get_loc(d) - 1
                    if prev >= 0:
                        daily.loc[d] += direction * (ew.loc[d] - ew.iloc[prev])
        cum = daily.cumsum()
        fig.add_trace(go.Scatter(x=cum.index, y=cum.values,
                                  name="Cum cell P&L (bbl)", line=dict(color="darkblue", width=1.2)),
                        row=2, col=1)

    fig.update_layout(height=640, margin=dict(t=30, b=20, l=10, r=10),
                       legend=dict(orientation="h", yanchor="top", y=-0.05))
    fig.update_xaxes(title_text="Date", row=2, col=1,
                       rangeslider=dict(visible=True, thickness=0.06),
                       rangeselector=dict(buttons=[
                           dict(count=3, label="3M", step="month", stepmode="backward"),
                           dict(count=6, label="6M", step="month", stepmode="backward"),
                           dict(count=1, label="1Y", step="year", stepmode="backward"),
                           dict(count=2, label="2Y", step="year", stepmode="backward"),
                           dict(step="all", label="All"),
                       ], y=1.10, x=0.0))
    fig.update_xaxes(range=[r_start, r_end], row=1, col=1)
    fig.update_xaxes(range=[r_start, r_end], row=2, col=1)
    fig.update_yaxes(title_text="spread", row=1, col=1)
    fig.update_yaxes(title_text="Cum P&L (bbl)", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # Recent closed trades in Y
    if not trades.empty:
        st.markdown(f"**Trades in Y{YEAR}**")
        trades_y = trades[trades["entry_date"].dt.year == YEAR].sort_values("entry_date")
        cols_show = ["entry_date", "exit_date", "side", "entry", "exit", "pnl",
                       "max_loss", "holding_bd", "exit_reason"]
        cols_avail = [c for c in cols_show if c in trades_y.columns]
        show = trades_y[cols_avail].copy()
        if "entry_date" in show: show["entry_date"] = show["entry_date"].dt.date
        if "exit_date" in show: show["exit_date"] = show["exit_date"].dt.date
        st.dataframe(show, use_container_width=True, hide_index=True)

    # Cell metadata
    st.markdown(f"**Cell**: `{sel['cell']}`")
    m = CELL_RE.match(sel["cell"])
    if m:
        fname, W, SE, SL, SLP = m.groups()
        st.caption(f"Family={sel['family']}  ·  W={W}M  ·  SE={SE}  ·  SL={SL}  ·  Fname={fname}")
    if str(sel["family"]).startswith("IP_"):
        st.warning("This is an **Inter-Product** diff — not in production's universe today.")


# ── Footer ─────────────────────────────────────────────
st.divider()
st.caption(
    f"Backtest window: {first_bar.date()} → {last_bar.date()}  ·  "
    f"Bundled from analytics/portfolio_MPT_entry_var_SHADOW.xlsx  ·  "
    f"Refresh: analytics/_apply_mpt_entry_var_shadow.py + _bundle_shadow_drilldown_data.py"
)
