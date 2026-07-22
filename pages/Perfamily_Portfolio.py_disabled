"""Per-family Portfolio Explorer — Dist only (presentation build).

Reads precomputed per-family backtest data from data/perfamily_<F>.json
(no live picker — works on Streamlit Cloud without backend access).

Sections:
  1. Family + Year selectors (dropdown — D only for now)
  2. Cap-Sharpe / Sortino / Calmar curve + metrics table
  3. MPT portfolio for selected cap (cap slider)
  4. Custom multiselect (pick top-1 cells per diff — rebalance MVP)
"""
from __future__ import annotations
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Per-Family Portfolio", layout="wide")

# ── Paths ─────────────────────────────────────────────────────────
PAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PAGE_DIR.parent / "data"

FAMILY_LABEL = {"D": "Distillates",
                 "L": "Lights",
                 "F": "Fuel Oil",
                 "C": "Crude"}
AVAILABLE_FAMILIES = ["L", "D", "F", "C"]   # all 4 families bundled


@st.cache_data(ttl=900)
def load_family_data(family: str) -> dict:
    fp = DATA_DIR / f"perfamily_{family}.json"
    if not fp.exists():
        return {}
    return json.loads(fp.read_text())


@st.cache_data(ttl=900)
def load_cell_universe(family: str) -> tuple[pd.DataFrame, dict]:
    """Load the wide-format per-cell daily P&L and metadata for a family."""
    fp = DATA_DIR / "perfamily" / family / "cells.parquet"
    meta_fp = DATA_DIR / "perfamily" / family / "meta.json"
    if not fp.exists() or not meta_fp.exists():
        return pd.DataFrame(), {}
    df = pd.read_parquet(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    meta = json.loads(meta_fp.read_text())
    return df, meta


def _solve_max_sharpe(mu: np.ndarray, Sigma: np.ndarray) -> np.ndarray:
    """SLSQP max-Sharpe with weights summing to 1 in [0, 1]."""
    from scipy.optimize import minimize
    N = len(mu)
    def neg_sharpe(w):
        ret = float(w @ mu)
        vol = float(np.sqrt(max(w @ Sigma @ w, 1e-12)))
        return -ret / vol if vol > 0 else 0.0
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(0.0, 1.0)] * N
    w0 = np.ones(N) / N
    result = minimize(neg_sharpe, w0, method="SLSQP", bounds=bounds,
                       constraints=constraints,
                       options={"ftol": 1e-9, "maxiter": 500})
    w = np.clip(result.x if result.success else w0, 0.0, 1.0)
    s = w.sum()
    return w / s if s > 0 else w


def run_mpt_on_subset(cells_df: pd.DataFrame, cell_ids: list[str],
                       year: int) -> dict:
    """Run MPT on selected cells, OOS year = `year`, IS = prior 5 yrs.

    Returns dict with weights, daily_pnl (OOS year), metrics.
    """
    from sklearn.covariance import LedoitWolf
    if not cell_ids:
        return {}
    # Date filter — must use prior 5 years for the MPT solve
    df = cells_df[["Date"] + cell_ids].copy()
    df = df.dropna(how="all", subset=cell_ids).set_index("Date")
    is_start = pd.Timestamp(year - 5, 1, 1)
    is_end = pd.Timestamp(year - 1, 12, 31)
    is_df = df[(df.index >= is_start) & (df.index <= is_end)].fillna(0.0)
    if is_df.empty or len(is_df) < 100:
        return {"error": "Not enough in-sample data."}
    mu = is_df.values.mean(axis=0)
    Sigma = LedoitWolf().fit(is_df.values).covariance_
    w = _solve_max_sharpe(mu, Sigma)
    # OOS year P&L
    oos_start = pd.Timestamp(year, 1, 1)
    oos_end = pd.Timestamp(year, 12, 31)
    oos_df = df[(df.index >= oos_start) & (df.index <= oos_end)].fillna(0.0)
    if oos_df.empty:
        oos_pnl = pd.Series(dtype=float)
    else:
        oos_pnl = pd.Series(oos_df.values @ w, index=oos_df.index)
    return {
        "weights": dict(zip(cell_ids, w)),
        "oos_pnl": oos_pnl,
        "is_n_days": len(is_df),
        "mu": mu, "shrinkage": float(LedoitWolf().fit(is_df.values).shrinkage_),
    }


def perf_metrics(s: pd.Series) -> dict:
    """Compute standard performance metrics from a daily-P&L series."""
    s = s.dropna()
    if s.empty:
        return {}
    cum = s.cumsum()
    peak = cum.cummax()
    dd = cum - peak
    ann_ret = float(s.mean() * 252)
    ann_vol = float(s.std() * np.sqrt(252))
    sharpe = ann_ret / ann_vol if ann_vol > 0 else float("nan")
    neg = s[s < 0]
    dn_std = float(neg.std()) if len(neg) > 1 else 0.0
    sortino = (ann_ret / (dn_std * np.sqrt(252))
                if dn_std > 0 else float("nan"))
    return {
        "n_days": int(len(s)),
        "total_pnl": float(s.sum()),
        "sharpe": sharpe, "sortino": sortino,
        "max_dd": float(dd.min()),
        "calmar": (ann_ret / abs(float(dd.min()))
                    if dd.min() < 0 else float("nan")),
        "win_day_pct": float((s > 0).mean() * 100),
    }


# ── Page header ──────────────────────────────────────────────────
st.title("Per-Family Portfolio Explorer")
st.caption("Cap exploration · MPT mean-variance portfolios · Custom subset rebalancing")
st.divider()

# ── Sidebar ───────────────────────────────────────────────────────
st.sidebar.header("Filters")
fam = st.sidebar.selectbox(
    "Family",
    options=AVAILABLE_FAMILIES,
    format_func=lambda x: f"{x} — {FAMILY_LABEL[x]}",
    index=0,
)
st.sidebar.caption("Lights · Distillates · Fuel Oil · Crude — switch any time.")

data = load_family_data(fam)
if not data:
    st.error(f"No data file found for {fam}. Expected: data/perfamily_{fam}.json")
    st.stop()

years = data["years"]
oos_year = st.sidebar.selectbox("OOS Year", options=years[::-1], index=0)

st.sidebar.divider()
st.sidebar.markdown(f"**Family:** {FAMILY_LABEL[fam]}  ")
st.sidebar.markdown(f"**Year:** {oos_year}  ")

# ── Universe overview ────────────────────────────────────────────
diff_list = data["diff_list"]
universe_year = data["universe_by_year"].get(str(oos_year), [])

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Universe (n diffs)", len(diff_list))
with c2:
    st.metric("Top-1 cells (year)", len(universe_year))
with c3:
    n_caps = len(data["cap_results"])
    st.metric("Caps tested", n_caps)

st.divider()

# ── SECTION 1: Cap-Sharpe curve ──────────────────────────────────
st.header("1. Cap exploration — performance across caps")
st.caption("Sharpe / Sortino / Calmar curves across cap values. Right shoulder is the robust pick.")

# Build cap table from cap_results
cap_rows = []
for cap_str, cap_data in data["cap_results"].items():
    # Find TOTAL metrics
    metrics = cap_data["metrics"]
    tot = next((m for m in metrics if m["label"] == f"{fam}_TOTAL"), None)
    if tot is None:
        continue
    n_year = len(cap_data["weights_by_year"].get(str(oos_year), []))
    weights_year = cap_data["weights_by_year"].get(str(oos_year), [])
    if weights_year:
        w_arr = np.array([w["weight"] for w in weights_year])
        n_eff = 1.0 / float((w_arr ** 2).sum())
    else:
        n_eff = 0
    cap_rows.append({
        "cap": cap_str,
        "n_picks_year": n_year,
        "n_eff": n_eff,
        "total_pnl": tot["total_pnl"],
        "sharpe": tot["sharpe"],
        "sortino": tot["sortino"],
        "max_dd": tot["max_drawdown"],
        "calmar": tot["calmar"],
        "win_day": tot["win_day_pct"],
    })
cap_df = pd.DataFrame(cap_rows)

# Sort by cap value (numeric first, then nocap)
def cap_sort_key(c):
    return 100 if c == "nocap" else int(c)
cap_df["sort_k"] = cap_df["cap"].map(cap_sort_key)
cap_df = cap_df.sort_values("sort_k").reset_index(drop=True)

# Plotly cap-sweep chart
fig_cap = go.Figure()
x_labels = cap_df["cap"].astype(str).tolist()
fig_cap.add_trace(go.Scatter(
    x=x_labels, y=cap_df["sharpe"],
    name="Sharpe", mode="lines+markers",
    line=dict(color="steelblue", width=2.5),
    marker=dict(size=10, symbol="circle"),
))
fig_cap.add_trace(go.Scatter(
    x=x_labels, y=cap_df["sortino"],
    name="Sortino", mode="lines+markers",
    line=dict(color="seagreen", width=2),
    marker=dict(size=9, symbol="square"),
))
fig_cap.add_trace(go.Scatter(
    x=x_labels, y=cap_df["calmar"],
    name="Calmar", mode="lines+markers",
    line=dict(color="darkorange", width=2),
    marker=dict(size=9, symbol="triangle-up"),
))
fig_cap.add_hline(y=0, line=dict(color="grey", width=0.7))
fig_cap.update_layout(
    height=420,
    margin=dict(t=50, b=20, l=10, r=10),
    title=dict(
        text=f"<b>{FAMILY_LABEL[fam]} — Cap sweep (TOTAL, 2021–2026 OOS)</b>",
        font=dict(size=13),
    ),
    legend=dict(orientation="h", yanchor="top", y=-0.1),
    xaxis_title="Cap (max picks)",
    yaxis_title="Risk-adjusted return",
    plot_bgcolor="white",
    hovermode="x unified",
)
fig_cap.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
fig_cap.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
st.plotly_chart(fig_cap, use_container_width=True)

# Table
st.subheader("Cap-sweep metrics table")
show_df = cap_df.drop(columns=["sort_k"]).copy()
show_df["sharpe"] = show_df["sharpe"].round(2)
show_df["sortino"] = show_df["sortino"].round(2)
show_df["max_dd"] = show_df["max_dd"].round(2)
show_df["calmar"] = show_df["calmar"].round(2)
show_df["total_pnl"] = show_df["total_pnl"].round(2)
show_df["win_day"] = show_df["win_day"].round(1)
show_df["n_eff"] = show_df["n_eff"].round(2)
st.dataframe(show_df, use_container_width=True, hide_index=True)

st.divider()

# ── SECTION 2: MPT portfolio for chosen cap ──────────────────────
st.header("2. MPT portfolio for selected cap")
st.caption(f"Pick a cap; below is the MPT-optimised portfolio for {FAMILY_LABEL[fam]} Y{oos_year}.")

cap_options_str = cap_df["cap"].tolist()
cap_choice = st.select_slider("Cap", options=cap_options_str, value="5")

# Pull metrics + weights for selected cap
sel_cap = data["cap_results"].get(cap_choice, {})
if not sel_cap:
    st.warning(f"No data for cap={cap_choice}")
else:
    weights_year = sel_cap["weights_by_year"].get(str(oos_year), [])
    metrics = sel_cap["metrics"]
    m_total = next((m for m in metrics if m["label"] == f"{fam}_TOTAL"), {})
    m_year = next((m for m in metrics if m["label"] == f"{fam}_Y{oos_year}"), {})

    if not weights_year:
        st.info(f"No picks for cap={cap_choice}, Y{oos_year}.")
    else:
        w_df = pd.DataFrame(weights_year).sort_values("weight", ascending=False)
        n_eff = 1.0 / float((w_df["weight"] ** 2).sum())

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        with mc1:
            st.metric("Picks", len(w_df))
        with mc2:
            st.metric("N_eff", f"{n_eff:.2f}")
        with mc3:
            st.metric("TOTAL Sharpe", f"{m_total.get('sharpe', 0):.2f}")
        with mc4:
            st.metric("TOTAL Max DD", f"{m_total.get('max_drawdown', 0):.2f}")
        with mc5:
            st.metric(f"Y{oos_year} P&L",
                       f"{m_year.get('total_pnl', 0):+.2f}")

        # Pick table
        st.subheader(f"Picks (cap={cap_choice}, Y{oos_year})")
        disp = w_df[["diff", "shape", "weight", "cell"]].copy()
        disp["weight"] = (disp["weight"] * 100).round(2).astype(str) + "%"
        st.dataframe(disp, use_container_width=True, hide_index=True)

        # Per-year metrics
        st.subheader("Per-year metrics")
        m_rows = [m for m in metrics if m["label"] != f"{fam}_TOTAL"]
        m_disp = pd.DataFrame(m_rows)
        if not m_disp.empty:
            m_disp["Year"] = m_disp["label"].str.replace(f"{fam}_Y", "")
            keep = ["Year", "n_days", "total_pnl", "sharpe", "sortino",
                     "max_drawdown", "calmar", "win_day_pct"]
            m_disp = m_disp[keep].round(3)
            st.dataframe(m_disp, use_container_width=True, hide_index=True)

        # Equity curve (Plotly)
        st.subheader("Cumulative P&L (yearly reset)")
        daily = pd.DataFrame(sel_cap["daily_pnl"])
        if not daily.empty:
            daily["Date"] = pd.to_datetime(daily["Date"])
            daily = daily.set_index("Date")["pnl"].sort_index()
            yr_cum = daily.groupby(daily.index.year).cumsum()

            COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                       "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
            fig_eq = go.Figure()
            for i, Y in enumerate(sorted(daily.index.year.unique())):
                mask = daily.index.year == Y
                sub = yr_cum[mask]
                if sub.empty:
                    continue
                col = COLORS[i % len(COLORS)]
                fig_eq.add_trace(go.Scatter(
                    x=sub.index, y=sub.values,
                    name=f"Y{Y}",
                    mode="lines",
                    line=dict(color=col, width=1.7),
                    fill="tozeroy",
                    fillcolor=col.replace("rgb(", "rgba(").replace(")", ",0.10)")
                                if col.startswith("rgb")
                                else f"rgba(0,0,0,0.05)",
                    hovertemplate=f"<b>Y{Y}</b><br>"
                                    "%{x|%Y-%m-%d}: $%{y:+.2f}<extra></extra>",
                ))
                # End-of-year value annotation
                last_v = float(sub.iloc[-1])
                fig_eq.add_annotation(
                    x=sub.index[-1], y=last_v,
                    text=f"<b>{last_v:+.1f}</b>",
                    showarrow=False, xshift=20,
                    font=dict(color=col, size=10),
                )
            fig_eq.add_hline(y=0, line=dict(color="grey", width=0.7))
            fig_eq.update_layout(
                height=420,
                margin=dict(t=50, b=20, l=10, r=40),
                title=dict(
                    text=f"<b>{FAMILY_LABEL[fam]} cap={cap_choice} — "
                          "yearly-reset cumulative P&L</b>",
                    font=dict(size=12),
                ),
                legend=dict(orientation="h", yanchor="top", y=-0.1),
                xaxis_title="Date",
                yaxis_title="Cumulative P&L",
                plot_bgcolor="white",
                hovermode="x unified",
            )
            fig_eq.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
            fig_eq.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
            st.plotly_chart(fig_eq, use_container_width=True)

st.divider()

# ── SECTION 3: Custom multiselect → live MPT solve ───────────────
st.header("3. Custom portfolio — multiselect + MPT")
st.caption(
    "Pick diffs to include. Each diff contributes its CLASSIFIER's top-1 cell "
    f"for Y{oos_year}. MPT re-solves on the selected subset using prior 5y "
    "(LedoitWolf shrunk covariance, max-Sharpe, weights ≥ 0, sum to 1)."
)

# Load cell universe
cells_df, cells_meta = load_cell_universe(fam)
if cells_df.empty:
    st.warning(
        f"Cell-level data missing for {fam}. Run "
        "`analytics/_export_perfamily_cell_data.py` and commit."
    )
elif not universe_year:
    st.info(f"No top-1 candidates for Y{oos_year}.")
else:
    options = [u["diff"] for u in universe_year]
    chosen = st.multiselect(
        f"Select diffs (top-1 cell of each for Y{oos_year}):",
        options=options,
        default=options[: min(5, len(options))],
    )
    if len(chosen) < 2:
        st.info("Select at least 2 diffs to run MPT.")
    else:
        chosen_rows = [u for u in universe_year if u["diff"] in chosen]
        cell_ids = [r["cell"] for r in chosen_rows]
        missing = [c for c in cell_ids if c not in cells_df.columns]
        if missing:
            st.warning(
                f"{len(missing)} cell(s) not in bundled data: "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''}. "
                "Re-run `_export_perfamily_cell_data.py`."
            )
            cell_ids = [c for c in cell_ids if c in cells_df.columns]
        if len(cell_ids) < 2:
            st.info("Need at least 2 cells with available data.")
        else:
            with st.spinner(f"Solving MPT on {len(cell_ids)} cells…"):
                result = run_mpt_on_subset(cells_df, cell_ids, int(oos_year))
            if result.get("error"):
                st.error(result["error"])
            else:
                weights = result["weights"]
                oos_pnl = result["oos_pnl"]
                # Display weights
                disp_rows = []
                for u in chosen_rows:
                    cid = u["cell"]
                    if cid in weights:
                        disp_rows.append({
                            "diff": u["diff"], "shape": u["shape"],
                            "cell": cid,
                            "weight": weights[cid],
                            "P_winner": u.get("P_winner"),
                        })
                w_df = pd.DataFrame(disp_rows).sort_values(
                    "weight", ascending=False
                )
                n_eff = 1.0 / float((w_df["weight"] ** 2).sum())

                # Compute IS metrics (prior 5y portfolio P&L)
                is_start = pd.Timestamp(int(oos_year) - 5, 1, 1)
                is_end = pd.Timestamp(int(oos_year) - 1, 12, 31)
                is_df = (cells_df[["Date"] + cell_ids]
                          .dropna(how="all", subset=cell_ids)
                          .set_index("Date"))
                is_sub = is_df[(is_df.index >= is_start)
                                & (is_df.index <= is_end)].fillna(0.0)
                w_vec = np.array([weights[c] for c in cell_ids])
                is_pnl = pd.Series(is_sub.values @ w_vec, index=is_sub.index)

                # Metric strip
                m_is = perf_metrics(is_pnl)
                m_oos = perf_metrics(oos_pnl)
                mm1, mm2, mm3, mm4, mm5, mm6 = st.columns(6)
                with mm1:
                    st.metric("Picks", len(w_df))
                with mm2:
                    st.metric("N_eff", f"{n_eff:.2f}")
                with mm3:
                    st.metric("Shrinkage", f"{result['shrinkage']:.3f}")
                with mm4:
                    st.metric("IS Sharpe (5y)", f"{m_is.get('sharpe', 0):.2f}")
                with mm5:
                    st.metric(f"OOS Y{oos_year} P&L",
                               f"{m_oos.get('total_pnl', 0):+.2f}")
                with mm6:
                    st.metric(f"OOS Y{oos_year} Sharpe",
                               f"{m_oos.get('sharpe', 0):.2f}")

                # Pick table with weights
                st.subheader("Solved weights")
                disp = w_df[["diff", "shape", "weight", "cell"]].copy()
                disp["weight"] = (disp["weight"] * 100).round(2).astype(str) + "%"
                st.dataframe(disp, use_container_width=True, hide_index=True)

                # OOS equity curve
                if not oos_pnl.empty:
                    st.subheader(f"OOS Y{oos_year} cumulative P&L")
                    cum = oos_pnl.cumsum()
                    fig_oos = go.Figure()
                    fig_oos.add_trace(go.Scatter(
                        x=cum.index, y=cum.values,
                        mode="lines",
                        line=dict(color="#1f77b4", width=2),
                        fill="tozeroy",
                        fillcolor="rgba(31,119,180,0.10)",
                        name=f"Custom MPT (cap={len(cell_ids)})",
                        hovertemplate="%{x|%Y-%m-%d}: $%{y:+.2f}<extra></extra>",
                    ))
                    fig_oos.add_hline(y=0, line=dict(color="grey", width=0.7))
                    fig_oos.update_layout(
                        height=380,
                        margin=dict(t=40, b=20, l=10, r=10),
                        title=dict(
                            text=f"<b>Custom subset MPT — OOS Y{oos_year}</b>",
                            font=dict(size=12),
                        ),
                        xaxis_title="Date",
                        yaxis_title="Cumulative P&L",
                        plot_bgcolor="white",
                        hovermode="x unified",
                    )
                    fig_oos.update_xaxes(showgrid=True,
                                          gridcolor="rgba(0,0,0,0.06)")
                    fig_oos.update_yaxes(showgrid=True,
                                          gridcolor="rgba(0,0,0,0.06)")
                    st.plotly_chart(fig_oos, use_container_width=True)

st.divider()

st.caption(
    f"Data source: `data/perfamily_{fam}.json` "
    "(precomputed from `portfolio_MPT_perfamily_cap5_all.xlsx` + "
    "`top1_picks_per_year_v2.xlsx` + `analytics/mpt_cache/`)."
)
