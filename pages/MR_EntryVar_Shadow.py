"""SHADOW methodology page — MPT re-solved on entry-VaR-scaled $-P&L.

Compares against production picks side-by-side. Purely diagnostic — production
is not touched. Bundled parquet data lives under Streamlit_v1/data/entry_var_shadow/.
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
    if not fp.exists():
        return pd.DataFrame()
    return pd.read_parquet(fp)


# ── Data ──────────────────────────────────────────────────
shadow_w = load_parquet("shadow_weights")
shadow_m = load_parquet("shadow_metrics")
shadow_d = load_parquet("shadow_daily_pnl")
prod_w = load_parquet("prod_weights")
prod_m = load_parquet("prod_metrics")
prod_d = load_parquet("prod_daily_pnl")

if shadow_w.empty:
    st.error("Shadow data not bundled. Regenerate via analytics/_apply_mpt_entry_var_shadow.py "
             "and re-bundle to data/entry_var_shadow/.")
    st.stop()

# ── Title + intro ────────────────────────────────────────
st.title("Mean Reversion — Shadow MPT (Entry-VaR-Scaled $-P&L)")
st.caption(
    "Purely diagnostic backtest — production MPT-7 v2 is NOT touched. This page shows what MPT WOULD have picked "
    "if the covariance/mean matrix used entry-day-VaR-scaled DOLLAR P&L instead of per-bbl P&L. Includes IP diffs in the universe."
)

with st.expander("What is 'shadow' methodology?"):
    st.markdown(
        """
Production MPT-7 v2 today:
- Optimizes weights on per-bbl daily P&L covariance
- Sizes each pick's position at year-start VaR
- Portfolio P&L reported in bbl-weighted units

**Shadow methodology (this page):**
- For each candidate cell, historical daily P&L is first sized by 1/VaR99_at_trade_entry (dollar terms)
- MPT solves max-Sharpe on this dollar-P&L covariance
- Picks the top-7 diff-unique cells with positive weights
- Backtest OOS with the shadow picks

**Result:** if $-Sharpe MPT chooses different picks than bbl-Sharpe MPT, we see it here. No lookahead —
each year's MPT solve uses only Y-5 to Y-1 data (explicit leak-assertion in the code).
        """
    )

# ── Portfolio metrics comparison ─────────────────────────
st.subheader("Portfolio metrics — Shadow vs Production")

def merge_metrics(prod_m, shadow_m):
    prod_m = prod_m.set_index("label")
    shadow_m = shadow_m.set_index("label")
    rows = []
    for lbl in sorted(prod_m.index.union(shadow_m.index)):
        prod_r = prod_m.loc[lbl] if lbl in prod_m.index else None
        shad_r = shadow_m.loc[lbl] if lbl in shadow_m.index else None
        rows.append({
            "label": lbl,
            "prod_total_pnl": float(prod_r["total_pnl"]) if prod_r is not None else np.nan,
            "shadow_total_pnl": float(shad_r["total_pnl"]) if shad_r is not None else np.nan,
            "prod_sharpe": float(prod_r["sharpe"]) if prod_r is not None else np.nan,
            "shadow_sharpe": float(shad_r["sharpe"]) if shad_r is not None else np.nan,
            "prod_max_dd": float(prod_r["max_drawdown"]) if prod_r is not None else np.nan,
            "shadow_max_dd": float(shad_r["max_drawdown"]) if shad_r is not None else np.nan,
            "shadow_win_day": float(shad_r["win_day_pct"]) if shad_r is not None else np.nan,
        })
    return pd.DataFrame(rows)

cmp = merge_metrics(prod_m, shadow_m)
# Move TOTAL to top
cmp = pd.concat([cmp[cmp["label"] == "TOTAL"], cmp[cmp["label"] != "TOTAL"]]).reset_index(drop=True)

# Delta columns
cmp["Δ Total P&L"] = cmp["shadow_total_pnl"] - cmp["prod_total_pnl"]
cmp["Δ Sharpe"] = cmp["shadow_sharpe"] - cmp["prod_sharpe"]

st.dataframe(
    cmp.rename(columns={
        "label": "Year",
        "prod_total_pnl": "Prod P&L",
        "shadow_total_pnl": "Shadow P&L",
        "prod_sharpe": "Prod Sharpe",
        "shadow_sharpe": "Shadow Sharpe",
        "prod_max_dd": "Prod Max DD",
        "shadow_max_dd": "Shadow Max DD",
        "shadow_win_day": "Shadow Win-day %",
    }).round(3),
    use_container_width=True, hide_index=True,
)

# ── Cumulative equity curve ──────────────────────────────
st.subheader("Cumulative equity — Shadow vs Production")

shadow_d["Date"] = pd.to_datetime(shadow_d["Date"])
prod_d["Date"] = pd.to_datetime(prod_d["Date"])
shadow_cum = shadow_d.sort_values("Date").set_index("Date")["daily_pnl"].cumsum()
prod_cum = prod_d.sort_values("Date").set_index("Date")["daily_pnl"].cumsum()

fig_cum = go.Figure()
fig_cum.add_trace(go.Scatter(x=prod_cum.index, y=prod_cum.values,
                              name=f"Production (bbl-MPT)  ({prod_cum.iloc[-1]:+.2f})",
                              line=dict(color="#4C72B0", width=2)))
fig_cum.add_trace(go.Scatter(x=shadow_cum.index, y=shadow_cum.values,
                              name=f"Shadow ($-MPT + entry-VaR)  ({shadow_cum.iloc[-1]:+.2f})",
                              line=dict(color="#D62728", width=2)))
fig_cum.add_hline(y=0, line=dict(color="grey", width=0.6))
fig_cum.update_layout(
    height=440, margin=dict(t=30, b=20, l=10, r=10),
    xaxis_title="", yaxis_title="Cumulative P&L",
    legend=dict(orientation="h", yanchor="top", y=-0.05),
    hovermode="x unified",
)
st.plotly_chart(fig_cum, use_container_width=True)

# ── Picks per year — side by side ────────────────────────
st.subheader("Picks per year — Shadow vs Production")
years = sorted(shadow_w["Year"].unique())
sel_year = st.selectbox("Year", years, index=len(years) - 1)

col_p, col_s = st.columns(2)
with col_p:
    st.markdown(f"**Production picks — Y{sel_year}**")
    prod_yr = (prod_w[prod_w["Year"] == sel_year]
                 .sort_values("weight", ascending=False)
                 [["diff", "shape", "scenario", "weight"]]
                 .rename(columns={"scenario": "cell"}))
    prod_yr["weight"] = (prod_yr["weight"] * 100).round(2).astype(str) + "%"
    st.dataframe(prod_yr, use_container_width=True, hide_index=True)
with col_s:
    st.markdown(f"**Shadow picks — Y{sel_year}**")
    shad_yr = (shadow_w[shadow_w["Year"] == sel_year]
                 .sort_values("weight", ascending=False)
                 [["diff", "shape", "cell", "weight", "family"]])
    shad_yr["weight"] = (shad_yr["weight"] * 100).round(2).astype(str) + "%"
    # Highlight IP rows
    def highlight_ip(row):
        return ["background-color: #FFE9C4" if str(row["family"]).startswith("IP_") else ""
                 for _ in row]
    st.dataframe(shad_yr.style.apply(highlight_ip, axis=1),
                  use_container_width=True, hide_index=True)

# Overlap stat
prod_cells = set(prod_w[prod_w["Year"] == sel_year]["scenario"])
shad_cells = set(shadow_w[shadow_w["Year"] == sel_year]["cell"])
common = prod_cells & shad_cells
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Common cells", f"{len(common)} / 7")
with c2:
    prod_only = prod_cells - shad_cells
    st.metric("Prod-only", len(prod_only))
with c3:
    shad_only = shad_cells - prod_cells
    ip_in_shad = int((shadow_w[shadow_w["Year"] == sel_year]["family"]
                       .str.startswith("IP_")).sum())
    st.metric("Shadow IP picks", ip_in_shad)

if prod_only:
    st.markdown("**Cells only in production:**")
    st.code("\n".join(f"  {c}" for c in sorted(prod_only)))
if shad_only:
    st.markdown("**Cells only in shadow:**")
    st.code("\n".join(f"  {c}" for c in sorted(shad_only)))

# ── IP inclusion summary ─────────────────────────────────
st.subheader("IP diff inclusion in shadow picks")
ip_summary = (shadow_w.assign(is_ip=shadow_w["family"].str.startswith("IP_"))
                .groupby("Year")
                .agg(n_ip_picks=("is_ip", "sum"),
                       total_ip_weight=("weight",
                                        lambda s: s[shadow_w.loc[s.index, "is_ip"]].sum()))
                .reset_index())
ip_summary["total_ip_weight"] = (ip_summary["total_ip_weight"] * 100).round(2).astype(str) + "%"
st.dataframe(ip_summary, use_container_width=True, hide_index=True)
st.caption("IP diffs (Inter-Product spreads) are NOT in production's universe today. Shadow MPT includes them alongside "
            "the existing 4 families' diffs. RB-HO in particular is picked all 6 years.")

# ── Footer ───────────────────────────────────────────────
st.divider()
st.caption(
    "Bundled from: analytics/portfolio_MPT_entry_var_SHADOW.xlsx  ·  "
    "Regenerate via analytics/_apply_mpt_entry_var_shadow.py  ·  "
    "Comparison methodology: same top-5-per-family LogReg universe (with IP added), "
    "MPT re-solved on $-P&L covariance, top-7 diff-unique picks, weights renormalised."
)
