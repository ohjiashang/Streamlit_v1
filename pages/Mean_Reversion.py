"""MPT-7 v2 monitoring page.

Live tracking of the 7 Y2026 picks: active trades, current spread vs entry bands,
YTD portfolio P&L, drill-down per pick, and manual trade log for actual fills.

Data source: `BloombergCOT/analytics/monitor_state/mpt7_v2/` (refreshed by
`_monitor_refresh_mpt7.py`).
"""
from __future__ import annotations

from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.mpt_monitor_helpers import (
    BLOOMBERG_COT, STATE_DIR, TRADE_LOG_FP, YEAR, LOCAL_MODE,
    load_state, load_pick_df, load_pick_trades, load_pick_open_trade,
    compute_daily_pnl, build_portfolio_daily_pnl,
    load_backtest_baseline_daily_pnl,
    derive_status_row, portfolio_metrics, spread_return_correlation,
    load_trade_log, save_trade_log_row, update_trade_log_row, delete_trade_log_row,
    run_refresh,
)

st.set_page_config(layout="wide", page_title="Mean Reversion V2")
st.title("Mean Reversion V2 - Y2026")

# ── Section A: Header strip ──────────────────────────────────────────
state = load_state()
if "error" in state:
    st.error(f"State not available: {state['error']}. Click Refresh below.")
    if st.button("Run full refresh now (data + state)", type="primary"):
        with st.spinner("Refreshing — this may take ~5 min..."):
            ok, log = run_refresh(include_data=True)
        st.text(log[-3000:])
        st.cache_data.clear()
        st.rerun()
    st.stop()

last_bar = pd.Timestamp(state["portfolio_last_bar"])
refreshed_at = datetime.fromisoformat(state["refreshed_at"])
staleness_bd = int(np.busday_count(last_bar.date(), date.today()))
banner_kind = "warning" if staleness_bd >= 3 else "info" if staleness_bd >= 2 else None

col_hdr_l, col_hdr_r = st.columns([3, 1])
with col_hdr_l:
    msg = (f"**As of:** {last_bar.date().isoformat()} "
           f"({staleness_bd} business day{'s' if staleness_bd != 1 else ''} stale)  "
           f"·  **Refreshed:** {refreshed_at.strftime('%Y-%m-%d %H:%M')}")
    if banner_kind == "warning":
        st.warning(msg + "  ·  ⚠️ Data is stale — refresh recommended")
    elif banner_kind == "info":
        st.info(msg)
    else:
        st.success(msg)
with col_hdr_r:
    if LOCAL_MODE:
        refresh_kind = st.radio("Refresh:", ["State only", "Full (data + state)"],
                                 horizontal=True, label_visibility="collapsed", index=0)
        if st.button("🔄 Refresh", use_container_width=True, type="primary"):
            with st.spinner("Refreshing — may take 1-5 min..."):
                ok, log = run_refresh(include_data=(refresh_kind == "Full (data + state)"))
            if ok:
                st.success("Refreshed + synced to Firebase.")
            else:
                st.error("Refresh failed.")
            with st.expander("Refresh log"):
                st.text(log[-5000:])
            st.cache_data.clear()
            st.rerun()
    else:
        if st.button("🔄 Reload from Firebase", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption("Cloud view (read-only)")

# Status rows for grid + metrics
status_rows = [derive_status_row(p) for p in state["picks"]]
status_df = pd.DataFrame(status_rows)

# Default sort: active trades first, then FLAT picks by ascending distance-to-entry σ
status_df["_is_flat"] = status_df["status"].str.startswith("FLAT")
status_df["_sort_dist"] = status_df["dist_to_entry_sigma"].fillna(float("inf"))
status_df = (status_df
             .sort_values(["_is_flat", "_sort_dist", "weight"],
                          ascending=[True, True, False])
             .drop(columns=["_is_flat", "_sort_dist"])
             .reset_index(drop=True))

# Portfolio metrics
port = build_portfolio_daily_pnl(YEAR)
metrics = portfolio_metrics(port["portfolio_daily_pnl"]) if not port.empty else portfolio_metrics(pd.Series(dtype=float))
baseline = load_backtest_baseline_daily_pnl(YEAR)
baseline_ytd = float(baseline.sum()) if not baseline.empty else np.nan

# Aggregate today's day P&L and total open MTM across picks
day_pnl_portfolio = float(status_df["daily_pnl_weighted"].sum())
open_pnl_portfolio = float(status_df["open_trade_pnl_weighted"].sum())
realised_ytd_portfolio = float(status_df["ytd_realised_weighted"].sum())
n_active = int(status_df["status"].str.startswith(("LONG", "SHORT")).sum())

c1, c2, c3, c4, c5, _ = st.columns([1, 1, 1, 1, 1, 3])
with c1:
    sign = "+" if day_pnl_portfolio >= 0 else "-"
    day_pnl_caption = f"{sign}${abs(day_pnl_portfolio):.3f}"
    st.metric("Unrealised P&L", f"${open_pnl_portfolio:+.3f}",
              delta=day_pnl_caption)
with c2:
    st.metric("Realised P&L", f"${realised_ytd_portfolio:+.3f}")
with c3:
    st.metric("YTD P&L", f"${metrics['ytd_pnl']:+.3f}")
with c4:
    st.metric("Sharpe", f"{metrics['sharpe']:.2f}" if not np.isnan(metrics['sharpe']) else "—")
with c5:
    st.metric("Active trades", f"{n_active} / {len(state['picks'])}")

st.divider()

# ── Section B: Portfolio status grid ─────────────────────────────────
st.subheader("Portfolio status")

def _row_color(row):
    alert = str(row.get("Signal alert", "") or "")
    status = str(row.get("Status", "") or "")
    if alert.startswith("FRESH"):
        return ["background-color: #ffe5b4"] * len(row)
    if alert.startswith("EXIT"):
        if "stop" in alert.lower():
            return ["background-color: #ffd6d6"] * len(row)
        return ["background-color: #d6ffd6"] * len(row)
    if status.startswith(("LONG", "SHORT")):
        return ["background-color: #FFFFE0"] * len(row)
    if status.startswith("FLAT"):
        return ["color: #888"] * len(row)
    return [""] * len(row)


def _pnl_color(v):
    if pd.isna(v) or v == 0:
        return ""
    return "color: darkgreen" if v > 0 else "color: darkred"


def _z_color(v):
    if pd.isna(v):
        return ""
    a = abs(v)
    if a < 0.3:
        return "color: green"
    if a < 1.0:
        return "color: #cc8800"
    return "color: red; font-weight: bold"


display_df = status_df[[
    "diff", "shape", "contract", "params", "weight",
    "current", "median",
    "status", "entry_date", "signal_alert",
    "daily_pnl_weighted", "open_trade_pnl_weighted", "ytd_realised_weighted",
]].copy()
display_df.columns = ["Diff", "Shape", "Contract", "Params", "Weight",
                      "Current", "Median",
                      "Status", "Entry date", "Signal alert",
                      "Day P&L", "Unrealised P&L", "Realised YTD P&L"]

styled = (display_df.style
          .format({"Weight": "{:.1%}", "Current": "{:.3f}", "Median": "{:.3f}",
                   "Day P&L": "${:+.3f}", "Unrealised P&L": "${:+.3f}",
                   "Realised YTD P&L": "${:+.3f}"})
          .apply(_row_color, axis=1)
          .map(_pnl_color, subset=["Day P&L", "Unrealised P&L", "Realised YTD P&L"]))
st.dataframe(
    styled, use_container_width=True, hide_index=True,
    column_config={
        "Diff": st.column_config.Column(width="small"),
        "Shape": st.column_config.Column(width="small"),
        "Contract": st.column_config.Column(width="medium"),
        "Params": st.column_config.Column(width="medium"),
        "Weight": st.column_config.Column(width="small"),
        "Current": st.column_config.Column(width="small"),
        "Median": st.column_config.Column(width="small"),
        "Status": st.column_config.Column(width="large"),
        "Entry date": st.column_config.Column(width="small"),
        "Signal alert": st.column_config.Column(width="medium"),
        "Day P&L": st.column_config.Column(width="small"),
        "Unrealised P&L": st.column_config.Column(width="small"),
        "Realised YTD P&L": st.column_config.Column(width="small"),
    },
)

# ── Section D: Portfolio P&L ─────────────────────────────────────────
st.subheader("Portfolio P&L (YTD)")
if not port.empty:
    pick_fnames = [p["fname"] for p in state["picks"]]
    cum = port["portfolio_daily_pnl"].cumsum()
    dd = cum - cum.cummax()

    col_left, col_right = st.columns([2, 1])
    with col_left:
        # Cumulative P&L (top) + Drawdown (bottom) sharing one x-axis
        last_x = cum.index[-1]
        last_y = float(cum.iloc[-1])
        fig_left = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07,
            row_heights=[0.6, 0.4],
            subplot_titles=(f"Cumulative P&L Y{YEAR}", f"Drawdown Y{YEAR}"),
        )
        fig_left.add_trace(
            go.Scatter(x=cum.index, y=cum.values, name="Live (YTD)",
                       line=dict(color="darkblue", width=2)),
            row=1, col=1,
        )
        fig_left.add_trace(
            go.Scatter(x=[last_x], y=[last_y],
                       mode="markers+text",
                       text=[f"<b>${last_y:+.3f}</b>"],
                       textposition="top left",
                       textfont=dict(size=14, color="darkblue"),
                       marker=dict(size=10, color="darkblue"),
                       showlegend=False,
                       hovertemplate=f"{last_x.date()}: ${last_y:+.3f}<extra></extra>"),
            row=1, col=1,
        )
        fig_left.add_hline(y=0, line=dict(color="grey", width=0.5), row=1, col=1)
        fig_left.add_trace(
            go.Scatter(x=dd.index, y=dd.values,
                       fill="tozeroy", fillcolor="rgba(255,0,0,0.2)",
                       line=dict(color="red", width=1), name="DD"),
            row=2, col=1,
        )
        fig_left.update_layout(height=640, margin=dict(t=40, b=20),
                                showlegend=False)
        st.plotly_chart(fig_left, use_container_width=True)
    with col_right:
        # Right top: YTD attribution
        attribution = port[pick_fnames].sum().sort_values()
        diff_map = {p["fname"]: f"{p['diff']} ({p['shape']})" for p in state["picks"]}
        fig_attr = go.Figure(go.Bar(x=attribution.values,
                                     y=[diff_map.get(f, f) for f in attribution.index],
                                     orientation="h",
                                     marker_color=["green" if v >= 0 else "red" for v in attribution.values]))
        fig_attr.update_layout(title="YTD attribution (weighted, by pick)",
                                height=350, margin=dict(t=40, b=20))
        st.plotly_chart(fig_attr, use_container_width=True)

        # Right bottom: Daily P&L bars (last 60 BD)
        last60 = port["portfolio_daily_pnl"].tail(60)
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(x=last60.index, y=last60.values,
                                  marker_color=["green" if v >= 0 else "red" for v in last60.values]))
        fig_bar.update_layout(title="Daily P&L (last 60 BD)", height=290,
                                margin=dict(t=40, b=20))
        st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── Section C: Drill-down ────────────────────────────────────────────
st.subheader("Drill-down per pick")
pick_labels = [f"{r['diff']} ({r['shape']})" for _, r in status_df.iterrows()]
selected_idx = st.selectbox("Pick", range(len(pick_labels)),
                             format_func=lambda i: pick_labels[i])

sel = status_df.iloc[selected_idx]
sel_meta = next(p for p in state["picks"] if p["fname"] == sel["fname"])
df = load_pick_df(sel["fname"])
trades = load_pick_trades(sel["fname"])
open_trade = load_pick_open_trade(sel["fname"])

# 18-month tail chart with bands + entries/exits
tail_start = df["Date"].max() - pd.DateOffset(months=18)
chart_df = df[df["Date"] >= tail_start].copy()
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                    row_heights=[0.7, 0.3])
fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["EW_adj"],
                          name="spread_normalised", line=dict(color="black", width=1.2)),
              row=1, col=1)
fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["rolling_median"],
                          name="median", line=dict(color="grey", width=1.0)),
              row=1, col=1)
fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["upper_bound"],
                          name="upper", line=dict(color="lightblue", width=0.8, dash="dot")),
              row=1, col=1)
fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["lower_bound"],
                          name="lower", line=dict(color="lightblue", width=0.8, dash="dot"),
                          fill="tonexty", fillcolor="rgba(173,216,230,0.15)"),
              row=1, col=1)

trades_tail = trades[trades["entry_date"] >= tail_start] if not trades.empty else trades
if not trades_tail.empty:
    longs = trades_tail[trades_tail["side"] == "long"]
    shorts = trades_tail[trades_tail["side"] == "short"]
    if not longs.empty:
        fig.add_trace(go.Scatter(x=longs["entry_date"], y=longs["entry"],
                                  mode="markers", name="long entry",
                                  marker=dict(symbol="triangle-up", size=10, color="green")),
                      row=1, col=1)
    if not shorts.empty:
        fig.add_trace(go.Scatter(x=shorts["entry_date"], y=shorts["entry"],
                                  mode="markers", name="short entry",
                                  marker=dict(symbol="triangle-down", size=10, color="red")),
                      row=1, col=1)
    fig.add_trace(go.Scatter(x=trades_tail["exit_date"], y=trades_tail["exit"],
                              mode="markers", name="exit",
                              marker=dict(symbol="x", size=8, color="black")),
                  row=1, col=1)
if open_trade is not None:
    fig.add_trace(go.Scatter(x=[open_trade["entry_date"]], y=[open_trade["entry_price"]],
                              mode="markers", name=f"OPEN {open_trade['side']}",
                              marker=dict(symbol="diamond", size=14,
                                          color="orange", line=dict(width=1.5, color="black"))),
                  row=1, col=1)

# pnl_running subplot (year-to-date slice)
pnl_running_ytd = chart_df[chart_df["Date"] >= pd.Timestamp(YEAR, 1, 1)]
fig.add_trace(go.Scatter(x=pnl_running_ytd["Date"], y=pnl_running_ytd["pnl_running"],
                          name="cum pnl (cell, since start)", line=dict(color="darkblue", width=1.0)),
              row=2, col=1)

fig.update_layout(height=600, margin=dict(t=30, b=20, l=10, r=10),
                  legend=dict(orientation="h", yanchor="top", y=-0.05))
fig.update_xaxes(title_text="Date", row=2, col=1)
fig.update_yaxes(title_text="spread_normalised", row=1, col=1)
fig.update_yaxes(title_text="Cum P&L", row=2, col=1)
st.plotly_chart(fig, use_container_width=True)

# Leg breakdown today
leg_cols = [c for c in df.columns
            if c not in {"Date", "EW", "EW_adj", "rolling_median", "rolling_std",
                          "upper_bound", "lower_bound", "contract", "pnl_running"}
            and not c.endswith("_contract")]
leg_contract_cols = [c for c in df.columns if c.endswith("_contract")]

if leg_cols:
    last_row = df.iloc[-1]
    leg_table = []
    for c in leg_cols:
        contract_col = f"{c}_contract"
        ctc = last_row.get(contract_col, "?") if contract_col in df.columns else "?"
        leg_table.append({"leg": c, "contract": ctc,
                          "signed_price": round(float(last_row[c]), 4)})
    leg_df = pd.DataFrame(leg_table)
    sum_legs = leg_df["signed_price"].sum()
    col_l, col_r = st.columns([1.5, 1])
    with col_l:
        st.markdown(f"**Leg breakdown — {sel_meta['formula']}**  ·  as of {last_bar.date()}")
        st.dataframe(leg_df, use_container_width=True, hide_index=True)
        st.caption(f"Σ signed legs = **{sum_legs:.4f}**  ·  EW = "
                   f"**{float(last_row['EW']):.4f}**  ·  spread_normalised (back-adj) = "
                   f"**{float(last_row['EW_adj']):.4f}**")
    with col_r:
        if open_trade is not None:
            st.markdown(f"**Open trade**")
            st.write({k: (v if not isinstance(v, pd.Timestamp) else v.date().isoformat())
                       for k, v in open_trade.items()})
        else:
            st.markdown("**Open trade**")
            st.caption("No open position (FLAT).")

# Last 10 closed trades
if not trades.empty:
    st.markdown("**Recent closed trades (last 10)**")
    cols_show = ["entry_date", "exit_date", "side", "entry", "exit", "pnl",
                 "max_loss", "holding_bd", "exit_reason"]
    show = trades.sort_values("exit_date", ascending=False).head(10)[cols_show]
    show = show.copy()
    show["entry_date"] = show["entry_date"].dt.date
    show["exit_date"] = show["exit_date"].dt.date
    st.dataframe(show, use_container_width=True, hide_index=True)

st.divider()

# ── Section G: Manual trade log ─────────────────────────────────────
# Hidden for now; flip SHOW_TRADE_LOG to True to re-enable.
SHOW_TRADE_LOG = False
if SHOW_TRADE_LOG:
    st.subheader("Live trade log")
    log = load_trade_log()
    log_y = log[(pd.to_datetime(log["entry_date"]).dt.year == YEAR) | (log["entry_date"].isna())]

    cols_lc, cols_rc = st.columns([1, 1])
    with cols_lc:
        st.caption(f"Stored at `{TRADE_LOG_FP}`")
    with cols_rc:
        show_view = st.radio("MTM source:", ["Signal-state (auto)", "Live (manual log)"],
                              horizontal=True, label_visibility="collapsed")

    # Discrepancy alerts
    disc = []
    for _, r in status_df.iterrows():
        if not r["status"].startswith("FLAT"):
            side = r["status"].split(" ")[0].lower()
            # Has a matching open live trade?
            open_match = log_y[(log_y["fname"] == r["fname"])
                                & (log_y["side"] == side)
                                & (log_y["closed"].isin([False, "False", "false", 0, np.nan]))]
            if open_match.empty:
                disc.append(f"⚠️ Signal says **{r['status']}** on **{r['diff']} ({r['shape']})** — no live entry logged.")
        else:
            # Is there an unclosed live trade for this cell whose signal is now flat?
            open_match = log_y[(log_y["fname"] == r["fname"])
                                & ~log_y["closed"].isin([True, "True", "true", 1])]
            if not open_match.empty:
                disc.append(f"⚠️ Live trade open on **{r['diff']} ({r['shape']})** but signal is now FLAT — log exit?")

    if disc:
        for d in disc:
            st.warning(d)

    # Entry form (local-only — trade log lives on the local machine)
    if not LOCAL_MODE:
        st.caption("Live trade log forms are local-only (Streamlit Cloud cannot write back to the source file).")
    if LOCAL_MODE:
        with st.expander("➕ Log a new fill (entry)"):
            f_pick = st.selectbox("Pick", range(len(pick_labels)),
                                  format_func=lambda i: pick_labels[i], key="log_entry_pick")
            f_row = status_df.iloc[f_pick]
            f_meta = next(p for p in state["picks"] if p["fname"] == f_row["fname"])
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                f_side = st.selectbox("Side", ["long", "short"], key="f_side")
                f_lots = st.number_input("Lots", value=1, min_value=1, key="f_lots")
            with col_f2:
                f_date = st.date_input("Entry date", value=last_bar.date(), key="f_date")
                f_signal = st.number_input("Signal price (spread_normalised at signal)",
                                            value=float(f_row["current"]), format="%.4f",
                                            key="f_signal")
            with col_f3:
                f_fill = st.number_input("Fill price (your actual exec)",
                                          value=float(f_row["current"]), format="%.4f",
                                          key="f_fill")
                f_slip = st.number_input("Slippage per leg ($)", value=0.10, format="%.4f",
                                          key="f_slip",
                                          help="Per-leg slippage estimate. Default 10c.")
            f_notes = st.text_input("Notes (optional)", key="f_notes")
            if st.button("Save entry", type="primary"):
                new_id = save_trade_log_row({
                    "fname": f_row["fname"], "cell": f_row["cell"],
                    "diff": f_row["diff"], "shape": f_row["shape"],
                    "weight": float(f_row["weight"]),
                    "side": f_side,
                    "entry_date": pd.Timestamp(f_date).isoformat(),
                    "entry_signal_price": f_signal,
                    "entry_fill_price": f_fill,
                    "entry_slippage_per_leg": f_slip,
                    "n_lots": int(f_lots),
                    "notes": f_notes,
                    "closed": False,
                })
                st.success(f"Logged trade {new_id}")
                st.rerun()

    # Open live trades — exit form
    open_live = log_y[~log_y["closed"].isin([True, "True", "true", 1])].copy()
    if LOCAL_MODE and not open_live.empty:
        with st.expander(f"🚪 Close an open live trade ({len(open_live)})"):
            choices = open_live.apply(
                lambda r: f"{r['trade_id'][:6]} · {r['diff']} ({r['shape']}) · "
                           f"{r['side']} @ {r['entry_fill_price']:.3f} "
                           f"on {pd.Timestamp(r['entry_date']).date()}", axis=1).tolist()
            sel_close = st.selectbox("Trade", range(len(choices)),
                                      format_func=lambda i: choices[i])
            chosen = open_live.iloc[sel_close]
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                x_date = st.date_input("Exit date", value=last_bar.date(), key="x_date")
            with col_c2:
                row_pick = status_df[status_df["fname"] == chosen["fname"]]
                cur_price = float(row_pick["current"].iloc[0]) if not row_pick.empty else 0.0
                x_signal = st.number_input("Signal price (exit)",
                                            value=cur_price, format="%.4f", key="x_signal")
                x_fill = st.number_input("Fill price (exit)",
                                          value=cur_price, format="%.4f", key="x_fill")
            with col_c3:
                x_slip = st.number_input("Exit slippage per leg ($)",
                                          value=0.10, format="%.4f", key="x_slip")
            if st.button("Close trade"):
                direction = 1.0 if chosen["side"] == "long" else -1.0
                pnl_realized = direction * (x_fill - chosen["entry_fill_price"]) * chosen["n_lots"]
                update_trade_log_row(chosen["trade_id"], {
                    "exit_date": pd.Timestamp(x_date).isoformat(),
                    "exit_signal_price": x_signal,
                    "exit_fill_price": x_fill,
                    "exit_slippage_per_leg": x_slip,
                    "closed": True,
                    "pnl_realized": round(pnl_realized, 4),
                })
                st.success(f"Closed {chosen['trade_id'][:6]} · realized P&L {pnl_realized:+.3f}")
                st.rerun()

    # Trade log table
    if not log_y.empty:
        show_cols = ["trade_id", "diff", "shape", "side", "n_lots",
                     "entry_date", "entry_signal_price", "entry_fill_price", "entry_slippage_per_leg",
                     "exit_date", "exit_signal_price", "exit_fill_price", "exit_slippage_per_leg",
                     "closed", "pnl_realized", "notes"]
        show = log_y[show_cols].copy()
        show["entry_date"] = pd.to_datetime(show["entry_date"]).dt.date
        show["exit_date"] = pd.to_datetime(show["exit_date"]).dt.date
        show["trade_id"] = show["trade_id"].str[:8]
        st.dataframe(show.sort_values("entry_date", ascending=False),
                     use_container_width=True, hide_index=True)
        csv = log_y.to_csv(index=False).encode("utf-8")
        st.download_button("Download trade log (CSV)", csv, "live_trade_log_y2026.csv",
                           "text/csv")
    else:
        st.caption("No live trades logged yet for Y2026.")

st.divider()

# ── Section E: Diagnostics ──────────────────────────────────────────
with st.expander("📊 Diagnostics (analyst)"):
    if not port.empty:
        pick_fnames = [p["fname"] for p in state["picks"]]
        st.markdown("**Realized vs backtest baseline**")
        if not baseline.empty:
            base_m = portfolio_metrics(baseline)
            comp = pd.DataFrame([
                {"metric": "YTD P&L", "live": f"{metrics['ytd_pnl']:+.3f}",
                 "backtest": f"{base_m['ytd_pnl']:+.3f}"},
                {"metric": "Sharpe", "live": f"{metrics['sharpe']:.2f}",
                 "backtest": f"{base_m['sharpe']:.2f}"},
                {"metric": "Max DD", "live": f"{metrics['max_dd']:.3f}",
                 "backtest": f"{base_m['max_dd']:.3f}"},
                {"metric": "Win rate", "live": f"{metrics['win_rate']:.1f}%",
                 "backtest": f"{base_m['win_rate']:.1f}%"},
                {"metric": "Best day", "live": f"{metrics['best_day']:.3f}",
                 "backtest": f"{base_m['best_day']:.3f}"},
                {"metric": "Worst day", "live": f"{metrics['worst_day']:.3f}",
                 "backtest": f"{base_m['worst_day']:.3f}"},
            ])
            st.dataframe(comp, use_container_width=True, hide_index=True)

        st.markdown("**Per-pick spread-return correlation (daily spread_normalised returns, trailing 12M)**")
        st.caption("Correlation of daily price moves of each spread, regardless of trade state. "
                   "Reflects underlying market co-movement (not realised P&L overlap).")
        corr = spread_return_correlation(window_months=12)
        if corr.empty:
            st.caption("Not enough data yet.")
        else:
            diff_map = {p["fname"]: f"{p['diff'][:8]} ({p['shape'][:4]})" for p in state["picks"]}
            corr.columns = [diff_map.get(c, c) for c in corr.columns]
            corr.index = [diff_map.get(c, c) for c in corr.index]
            fig_corr = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index,
                                              zmin=-1, zmax=1, colorscale="RdBu_r",
                                              text=np.round(corr.values, 2), texttemplate="%{text}"))
            fig_corr.update_layout(height=360, margin=dict(t=20, b=20))
            st.plotly_chart(fig_corr, use_container_width=True)

    # Realized slippage from trade log
    if not SHOW_TRADE_LOG:
        closed_log = pd.DataFrame()
    else:
        closed_log = log_y[log_y["closed"].isin([True, "True", "true", 1])]
    if not closed_log.empty:
        st.markdown("**Realized slippage from logged fills**")
        entry_slip = closed_log["entry_slippage_per_leg"].dropna().astype(float)
        exit_slip = closed_log["exit_slippage_per_leg"].dropna().astype(float)
        st.write({"n_closed": int(len(closed_log)),
                   "avg_entry_slip_per_leg": float(entry_slip.mean()) if len(entry_slip) else 0.0,
                   "avg_exit_slip_per_leg": float(exit_slip.mean()) if len(exit_slip) else 0.0})

