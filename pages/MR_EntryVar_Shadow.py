"""SHADOW methodology page — MPT re-solved on entry-VaR-scaled $-P&L.

Mirrors the main Mean Reversion page layout (scorecards, portfolio status grid,
charts, per-pick drilldown) but populated from the offline shadow backtest.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(page_title="MR — Entry-VaR Shadow", layout="wide")

ROOT = Path(__file__).resolve().parents[1] / "data" / "entry_var_shadow"


@st.cache_data(ttl=3600)
def load_parquet(name: str) -> pd.DataFrame:
    fp = ROOT / f"{name}.parquet"
    return pd.read_parquet(fp) if fp.exists() else pd.DataFrame()


# ── Data ──────────────────────────────────────────────────
shadow_w = load_parquet("shadow_weights")
shadow_m = load_parquet("shadow_metrics")
shadow_d = load_parquet("shadow_daily_pnl")
prod_m = load_parquet("prod_metrics")
prod_d = load_parquet("prod_daily_pnl")

if shadow_w.empty:
    st.error("Shadow data not bundled. Regenerate via analytics/_apply_mpt_entry_var_shadow.py.")
    st.stop()

shadow_d["Date"] = pd.to_datetime(shadow_d["Date"])
shadow_d = shadow_d.sort_values("Date").reset_index(drop=True)
prod_d["Date"] = pd.to_datetime(prod_d["Date"])
prod_d = prod_d.sort_values("Date").reset_index(drop=True)
shad_pnl_col = "daily_pnl" if "daily_pnl" in shadow_d.columns else "portfolio_daily_pnl"
prod_pnl_col = "portfolio_daily_pnl" if "portfolio_daily_pnl" in prod_d.columns else "daily_pnl"


# ── Header (mirrors main page style) ─────────────────────
years = sorted(shadow_w["Year"].unique())
last_date = shadow_d["Date"].max().date()
first_date = shadow_d["Date"].min().date()

col_hdr_l, col_hdr_r = st.columns([3, 1])
with col_hdr_l:
    st.title("Mean Reversion — Shadow (Entry-VaR $-MPT)")
    st.info(
        f"**Backtest window:** {first_date} → {last_date}  ·  "
        f"**{len(years)} OOS years**  ·  Diagnostic re-solve — production untouched"
    )
with col_hdr_r:
    st.metric("Total years", len(years))
    st.caption(f"Includes IP diffs in the candidate universe")


# ── Year selector (mirrors main page Year picker) ────────
YEAR = st.selectbox("Year", years, index=len(years) - 1,
                     help="Selects which OOS year to display picks + metrics for. "
                          "Cumulative equity chart always spans full 2021-2026 backtest.")


# ── Section A: Scorecards ────────────────────────────────
def metric_for_year(df_m, y):
    label = f"Y{y}"
    r = df_m[df_m["label"] == label]
    if r.empty: return None
    return r.iloc[0].to_dict()

def metric_total(df_m):
    r = df_m[df_m["label"] == "TOTAL"]
    return r.iloc[0].to_dict() if not r.empty else None

y_metrics = metric_for_year(shadow_m, YEAR)
total_metrics = metric_total(shadow_m)
prod_y_metrics = metric_for_year(prod_m, YEAR)

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
with c1:
    st.metric(f"Y{YEAR} Total P&L",
                f"${y_metrics['total_pnl']:+.3f}" if y_metrics else "—",
                delta=f"vs prod {y_metrics['total_pnl'] - prod_y_metrics['total_pnl']:+.3f}"
                        if y_metrics and prod_y_metrics else None)
with c2:
    st.metric("Sharpe",
                f"{y_metrics['sharpe']:.2f}" if y_metrics else "—",
                delta=f"vs prod {y_metrics['sharpe'] - prod_y_metrics['sharpe']:+.2f}"
                        if y_metrics and prod_y_metrics else None)
with c3:
    st.metric("Sortino", f"{y_metrics['sortino']:.2f}" if y_metrics else "—")
with c4:
    st.metric("Calmar",
                f"{y_metrics['calmar']:.2f}"
                if y_metrics and not pd.isna(y_metrics.get('calmar', np.nan)) else "—")
with c5:
    st.metric("Max DD", f"${y_metrics['max_drawdown']:+.3f}" if y_metrics else "—")
with c6:
    st.metric("Win-day %", f"{y_metrics['win_day_pct']:.1f}%" if y_metrics else "—")
with c7:
    st.metric("N picks", str(len(shadow_w[shadow_w["Year"] == YEAR])))

st.divider()


# ── Section B: Portfolio "status" grid (weights + family) ─
st.subheader(f"Portfolio picks — Y{YEAR}")
picks = (shadow_w[shadow_w["Year"] == YEAR]
           .sort_values("weight", ascending=False)
           .reset_index(drop=True))
picks_disp = picks[["diff", "shape", "cell", "weight", "family"]].copy()
picks_disp["weight"] = (picks_disp["weight"] * 100).round(2)
picks_disp["is_IP"] = picks_disp["family"].str.startswith("IP_")


def highlight_ip(row):
    if row.get("is_IP", False):
        return ["background-color: #FFF3CD"] * len(row)
    return [""] * len(row)


st.dataframe(
    picks_disp.rename(columns={
        "diff": "Diff", "shape": "Shape", "cell": "Cell",
        "weight": "Weight (%)", "family": "Family", "is_IP": "IP?"
    }).style.apply(highlight_ip, axis=1),
    use_container_width=True, hide_index=True,
    column_config={
        "Weight (%)": st.column_config.NumberColumn("Weight (%)", format="%.2f%%"),
    },
)

# Weight distribution bar
st.caption(f"IP diffs highlighted in yellow — {int(picks_disp['is_IP'].sum())} of {len(picks_disp)} picks this year.")


# ── Section C: Yearly-reset cumulative P&L chart ─────────
st.divider()
st.subheader("Yearly cumulative P&L — Shadow vs Production")

# Yearly-reset shadow
shad_series = shadow_d.set_index("Date")[shad_pnl_col]
prod_series = prod_d.set_index("Date")[prod_pnl_col]

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                     row_heights=[0.55, 0.45],
                     subplot_titles=("Yearly-reset cumulative equity",
                                       "Full-period cumulative (from 2021)"))

# Top: yearly-reset per year, shadow and prod overlaid
year_colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"]
for i, y in enumerate(years):
    shad_y = shad_series[shad_series.index.year == y].cumsum()
    prod_y = prod_series[prod_series.index.year == y].cumsum()
    color = year_colors[i % len(year_colors)]
    fig.add_trace(go.Scatter(x=shad_y.index, y=shad_y.values,
                              name=f"Shadow Y{y}",
                              line=dict(color=color, width=1.6),
                              legendgroup="shadow",
                              showlegend=(i == 0)),
                    row=1, col=1)
    fig.add_trace(go.Scatter(x=prod_y.index, y=prod_y.values,
                              name=f"Prod Y{y}",
                              line=dict(color=color, width=1.2, dash="dot"),
                              legendgroup="prod",
                              showlegend=(i == 0)),
                    row=1, col=1)

# Bottom: full-period cumulative
shad_cum = shad_series.cumsum()
prod_cum = prod_series.cumsum()
fig.add_trace(go.Scatter(x=prod_cum.index, y=prod_cum.values,
                          name=f"Prod (bbl-MPT)  ({prod_cum.iloc[-1]:+.2f})",
                          line=dict(color="#4C72B0", width=2.2)),
                row=2, col=1)
fig.add_trace(go.Scatter(x=shad_cum.index, y=shad_cum.values,
                          name=f"Shadow ($-MPT)  ({shad_cum.iloc[-1]:+.2f})",
                          line=dict(color="#D62728", width=2.2)),
                row=2, col=1)
fig.add_hline(y=0, line=dict(color="grey", width=0.5), row=2, col=1)
for y in years:
    fig.add_vline(x=pd.Timestamp(y, 1, 1), line=dict(color="grey", dash="dot", width=0.5),
                    row=1, col=1)

fig.update_layout(height=720, margin=dict(t=50, b=20, l=10, r=10),
                    legend=dict(orientation="h", yanchor="top", y=-0.06, x=0),
                    hovermode="x unified")
fig.update_yaxes(title_text="P&L ($)", row=1, col=1)
fig.update_yaxes(title_text="Cumulative P&L ($)", row=2, col=1)
st.plotly_chart(fig, use_container_width=True)


# ── Section D: Comparison metrics table ──────────────────
st.divider()
st.subheader("All-year metrics table")

def merge_all(prod_m, shadow_m):
    p = prod_m.set_index("label")
    s = shadow_m.set_index("label")
    rows = []
    order = ["TOTAL"] + [f"Y{y}" for y in years]
    for lbl in order:
        if lbl not in s.index: continue
        p_row = p.loc[lbl] if lbl in p.index else None
        s_row = s.loc[lbl]
        rows.append({
            "Year": lbl,
            "Prod P&L": p_row["total_pnl"] if p_row is not None else np.nan,
            "Shadow P&L": s_row["total_pnl"],
            "Δ P&L": (s_row["total_pnl"] - p_row["total_pnl"]) if p_row is not None else np.nan,
            "Prod Sharpe": p_row["sharpe"] if p_row is not None else np.nan,
            "Shadow Sharpe": s_row["sharpe"],
            "Δ Sharpe": (s_row["sharpe"] - p_row["sharpe"]) if p_row is not None else np.nan,
            "Prod Max DD": p_row["max_drawdown"] if p_row is not None else np.nan,
            "Shadow Max DD": s_row["max_drawdown"],
            "Shadow Win-day %": s_row["win_day_pct"],
        })
    return pd.DataFrame(rows).round(3)

st.dataframe(merge_all(prod_m, shadow_m), use_container_width=True, hide_index=True)


# ── Section E: Drilldown per pick (metadata + cell params) ─
st.divider()
st.subheader(f"Drilldown per pick — Y{YEAR}")
labels = [f"{r['diff']} ({r['shape']})  ·  w={r['weight']*100:.2f}%"
           for _, r in picks.iterrows()]
if labels:
    idx = st.selectbox("Pick", range(len(labels)),
                         format_func=lambda i: labels[i], key=f"drill_{YEAR}")
    p = picks.iloc[idx]

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.markdown(f"### {p['diff']} — {p['shape']}")
        # Parse cell params
        import re
        m = re.match(r"^(.+?)_W(\d+)M_SE([\d.]+)_SL([\d.]+)_SLP(\d+)$", p["cell"])
        if m:
            fname, W, SE, SL, SLP = m.groups()
            st.markdown(
                f"- **Cell**: `{p['cell']}`  \n"
                f"- **Fname / offsets**: `{fname}`  \n"
                f"- **Rolling window**: {W} months  \n"
                f"- **Entry σ (SE)**: {SE}  \n"
                f"- **Stop σ (SL)**: {SL}  \n"
                f"- **Family**: `{p['family']}`  \n"
                f"- **Weight**: {p['weight']*100:.2f}%  \n"
                f"- **MPT weight raw**: {p.get('mpt_weight_raw', float('nan')):.6f}"
            )
        else:
            st.write(p.to_dict())
    with col_b:
        st.markdown("### MPT diagnostics")
        st.markdown(
            f"- **P_winner** (LR): {p.get('P_winner', float('nan')):.4f}  \n"
            f"- **IS Sharpe**: {p.get('sharpe', float('nan')):.3f}  \n"
            f"- **IS PnL**: ${p.get('pnl', float('nan')):+.3f}  \n"
            f"- **IS Winrate**: {p.get('winrate', float('nan')):.1f}%  \n"
            f"- **N trades**: {int(p.get('n_trades', 0))}  \n"
            f"- **HL prior year**: {p.get('hl_prior_year', float('nan')):.1f}"
        )
        if str(p.get("family", "")).startswith("IP_"):
            st.warning("This is an **Inter-Product diff** — not in production's universe today.")


# ── Footer ───────────────────────────────────────────────
st.divider()
st.caption(
    f"Bundled from analytics/portfolio_MPT_entry_var_SHADOW.xlsx  ·  "
    f"Regenerate: analytics/_apply_mpt_entry_var_shadow.py  ·  "
    f"Methodology: same top-5-per-family LogReg universe (with IP added), "
    f"MPT re-solved on $-P&L covariance (each trade sized by 1/VaR99_at_entry), "
    f"top-7 diff-unique picks, weights renormalised."
)
