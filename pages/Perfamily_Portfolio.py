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
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Per-Family Portfolio", layout="wide")

# ── Paths ─────────────────────────────────────────────────────────
PAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PAGE_DIR.parent / "data"

FAMILY_LABEL = {"D": "Distillates",
                 "L": "Lights",
                 "F": "Fuel Oil",
                 "C": "Crude"}
AVAILABLE_FAMILIES = ["D"]  # extend later


@st.cache_data(ttl=900)
def load_family_data(family: str) -> dict:
    fp = DATA_DIR / f"perfamily_{family}.json"
    if not fp.exists():
        return {}
    return json.loads(fp.read_text())


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
st.sidebar.caption("Only Distillates available in this build. "
                    "Lights / Fuel Oil / Crude coming next.")

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

# Chart
fig, ax1 = plt.subplots(figsize=(11, 4.5))
x = list(range(len(cap_df)))
ax1.plot(x, cap_df["sharpe"], "o-", color="steelblue",
         linewidth=2.5, markersize=10, label="Sharpe")
ax1.plot(x, cap_df["sortino"], "s-", color="seagreen",
         linewidth=2, markersize=8, label="Sortino")
ax1.plot(x, cap_df["calmar"], "^-", color="darkorange",
         linewidth=2, markersize=8, label="Calmar")
ax1.set_xticks(x)
ax1.set_xticklabels(cap_df["cap"].astype(str))
ax1.set_xlabel("Cap (max picks)", fontsize=11)
ax1.set_ylabel("Risk-adjusted return", fontsize=11)
ax1.grid(alpha=0.3)
ax1.axhline(0, color="grey", linewidth=0.7)
ax1.legend(loc="upper left", fontsize=10)
ax1.set_title(f"{FAMILY_LABEL[fam]} — Cap sweep (TOTAL, 2021-2026 OOS)",
              fontsize=12, fontweight="bold")
st.pyplot(fig, clear_figure=True)

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

        # Equity curve
        st.subheader("Cumulative P&L (yearly reset)")
        daily = pd.DataFrame(sel_cap["daily_pnl"])
        if not daily.empty:
            daily["Date"] = pd.to_datetime(daily["Date"])
            daily = daily.set_index("Date")["pnl"].sort_index()
            yr_cum = daily.groupby(daily.index.year).cumsum()
            fig2, ax = plt.subplots(figsize=(12, 4))
            colors = plt.cm.tab10.colors
            for i, Y in enumerate(sorted(daily.index.year.unique())):
                mask = daily.index.year == Y
                sub = yr_cum[mask]
                if sub.empty:
                    continue
                color = colors[i % len(colors)]
                ax.plot(sub.index, sub.values, linewidth=1.6,
                         color=color, label=f"Y{Y}")
                ax.fill_between(sub.index, 0, sub.values,
                                 where=(sub.values >= 0), color=color, alpha=0.1)
                ax.fill_between(sub.index, 0, sub.values,
                                 where=(sub.values < 0), color=color, alpha=0.1)
                last_v = float(sub.iloc[-1])
                ax.annotate(f"{last_v:+.1f}", xy=(sub.index[-1], last_v),
                             xytext=(4, 0), textcoords="offset points",
                             fontsize=9, color=color, fontweight="bold",
                             va="center")
            ax.axhline(0, color="grey", linewidth=0.7)
            ax.grid(alpha=0.3)
            ax.legend(loc="upper left", ncol=3, fontsize=9)
            ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            ax.set_title(f"{FAMILY_LABEL[fam]} cap={cap_choice} — yearly-reset cumulative P&L",
                          fontsize=11, fontweight="bold")
            st.pyplot(fig2, clear_figure=True)

st.divider()

# ── SECTION 3: Custom multiselect ────────────────────────────────
st.header("3. Custom portfolio — multiselect")
st.caption(
    "Pick which diffs to include. Each diff contributes its CLASSIFIER's top-1 "
    f"cell for Y{oos_year}. Quick MPT re-solve coming next iteration."
)

if not universe_year:
    st.info(f"No top-1 candidates for Y{oos_year}.")
else:
    options = [u["diff"] for u in universe_year]
    chosen = st.multiselect(
        f"Select diffs (top-1 cell of each for Y{oos_year}):",
        options=options,
        default=options[: min(5, len(options))],
    )
    if not chosen:
        st.info("Select at least 2 diffs to continue.")
    else:
        chosen_rows = [u for u in universe_year if u["diff"] in chosen]
        st.caption(f"Selected {len(chosen_rows)} cells:")
        st.dataframe(
            pd.DataFrame(chosen_rows)[["diff", "shape", "cell", "P_winner"]],
            use_container_width=True, hide_index=True,
        )

        st.info(
            "**Custom MPT solve on this subset is the next iteration.** "
            "For now, you can see exactly which cells would be in scope and "
            "their classifier P_winner ranking. To approximate, use the "
            "cap slider above with cap ≈ number of diffs selected."
        )

st.divider()

st.caption(
    f"Data source: `data/perfamily_{fam}.json` "
    "(precomputed from `portfolio_MPT_perfamily_cap5_all.xlsx` + "
    "`top1_picks_per_year_v2.xlsx` + `analytics/mpt_cache/`)."
)
