"""Per-family Portfolio Explorer — Dist only (placeholder build).

Quick exploration UI for per-family MPT portfolios.

Sections:
  1. Family + Year selectors (dropdown — D only for now)
  2. Cap-Sharpe curve + per-year metrics table
  3. MPT portfolio for selected cap (cap slider)
  4. Custom multiselect (pick top-1 cells, MPT rebalances on subset)
"""
from __future__ import annotations
import io, json, sys
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

st.set_page_config(page_title="Per-Family Portfolio", layout="wide")

# ── Paths ─────────────────────────────────────────────────────────
ANALYTICS = Path(r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\BloombergCOT\analytics")
UNIVERSE_FP = ANALYTICS / "top1_picks_per_year_v2.xlsx"
CONFIG_FP = ANALYTICS / "perfamily_config.json"
RESULTS_FP = ANALYTICS / "portfolio_MPT_perfamily_cap5_all.xlsx"

# Add analytics to path for picker imports
if str(ANALYTICS) not in sys.path:
    sys.path.insert(0, str(ANALYTICS))


FAMILY_LABEL = {"D": "Distillates",
                 "L": "Lights",
                 "F": "Fuel Oil",
                 "C": "Crude"}


@st.cache_data(ttl=900)
def load_config():
    return json.loads(CONFIG_FP.read_text())


@st.cache_data(ttl=900)
def load_universe():
    return pd.read_excel(UNIVERSE_FP, sheet_name="ALL")


@st.cache_data(ttl=900)
def load_cap5_results():
    return pd.read_excel(RESULTS_FP, sheet_name=None)


@st.cache_data(ttl=900)
def run_cap_sweep(family: str, year: int, caps: list) -> pd.DataFrame:
    """Run MPT picker for each cap value. Returns per-(cap,year) metrics."""
    try:
        from _apply_mpt_perfamily import run_family
        cfg = load_config()
        diff_list = cfg["families"][family]
        ALL = load_universe()
        panels = {"__formula_idx__": {}}
        legs = {}
        rows = []
        for cap_val in caps:
            try:
                kwargs = ({"override_target": int(cap_val)}
                           if cap_val != "nocap"
                           else {"no_cap": True})
                r = run_family(family, diff_list, 3, ALL, panels, legs,
                                {}, {}, only_year=None, **kwargs)
                if r["metrics_df"].empty:
                    continue
                tot = r["metrics_df"][r["metrics_df"]["label"]
                                       == f"{family}_TOTAL"].iloc[0]
                w26 = r["weights_df"][r["weights_df"]["Y_OOS"] == year]
                n_eff = (1.0 / (w26["weight"] ** 2).sum()
                          if len(w26) else 0)
                rows.append({
                    "cap": cap_val,
                    "n_picks": len(w26),
                    "total_pnl": tot["total_pnl"],
                    "sharpe": tot["sharpe"],
                    "sortino": tot["sortino"],
                    "max_dd": tot["max_drawdown"],
                    "calmar": tot["calmar"],
                    "win_day": tot["win_day_pct"],
                    "n_eff": n_eff,
                })
            except Exception as e:
                st.warning(f"cap={cap_val} skipped: {e}")
        return pd.DataFrame(rows)
    except ImportError as e:
        st.error(f"Picker import failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=900)
def run_picker_for_cap(family: str, cap_val) -> dict:
    """Run MPT picker for a single cap value, return full result."""
    try:
        from _apply_mpt_perfamily import run_family
        cfg = load_config()
        diff_list = cfg["families"][family]
        ALL = load_universe()
        panels = {"__formula_idx__": {}}
        legs = {}
        kwargs = ({"override_target": int(cap_val)}
                   if cap_val != "nocap"
                   else {"no_cap": True})
        r = run_family(family, diff_list, 3, ALL, panels, legs,
                        {}, {}, only_year=None, **kwargs)
        return r
    except ImportError as e:
        st.error(f"Picker import failed: {e}")
        return {"weights_df": pd.DataFrame(),
                "daily": pd.Series(dtype=float),
                "metrics_df": pd.DataFrame()}


# ── Page header ──────────────────────────────────────────────────
st.title("Per-Family Portfolio Explorer")
st.caption("Cap exploration · MPT mean-variance portfolios · Custom subset rebalancing")
st.divider()

# ── Sidebar: family + year selector ──────────────────────────────
st.sidebar.header("Filters")
fam = st.sidebar.selectbox("Family",
                            options=["D"],  # only D for now
                            format_func=lambda x: f"{x} — {FAMILY_LABEL[x]}",
                            index=0)
st.sidebar.caption("Only Distillates available in this build. Lights / Fuel Oil / Crude coming next.")

oos_year = st.sidebar.selectbox("OOS Year",
                                  options=[2026, 2025, 2024, 2023, 2022, 2021],
                                  index=0)

st.sidebar.divider()
st.sidebar.markdown(f"**Family:** {FAMILY_LABEL[fam]}  ")
st.sidebar.markdown(f"**Year:** {oos_year}  ")

# ── Universe overview ────────────────────────────────────────────
cfg = load_config()
diff_list = cfg["families"][fam]
ALL = load_universe()
fam_univ = ALL[(ALL["diff"].isin(diff_list)) & (ALL["Y_OOS"] == oos_year)].copy()
fam_univ["fname"] = fam_univ["cell"].str.split("_W").str[0]

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Universe (n diffs)", len(diff_list))
with c2:
    st.metric("Candidate cells", len(fam_univ))
with c3:
    st.metric("Distinct shapes", fam_univ["shape"].nunique() if not fam_univ.empty else 0)

st.divider()

# ── SECTION 1: Cap-Sharpe curve ──────────────────────────────────
st.header("1. Cap exploration")
st.caption("Backtest Sharpe / Sortino / Max DD across caps. Right shoulder is the robust pick.")

CAPS_TO_TEST = [3, 4, 5, 6, 7, 8, 10, "nocap"]

with st.spinner("Computing cap sweep..."):
    cap_df = run_cap_sweep(fam, oos_year, CAPS_TO_TEST)

if cap_df.empty:
    st.warning("Cap-sweep computation failed.")
else:
    # Chart
    fig, ax1 = plt.subplots(figsize=(11, 4.5))
    x = list(range(len(cap_df)))
    ax1.plot(x, cap_df["sharpe"], "o-", color="steelblue",
              linewidth=2, markersize=8, label="Sharpe")
    ax1.plot(x, cap_df["sortino"], "s-", color="seagreen",
              linewidth=2, markersize=7, label="Sortino")
    ax1.plot(x, cap_df["calmar"], "^-", color="darkorange",
              linewidth=2, markersize=7, label="Calmar")
    ax1.set_xticks(x)
    ax1.set_xticklabels(cap_df["cap"].astype(str))
    ax1.set_xlabel("Cap")
    ax1.set_ylabel("Risk-adjusted return")
    ax1.grid(alpha=0.3)
    ax1.axhline(0, color="grey", linewidth=0.7)
    ax1.legend(loc="upper left")
    ax1.set_title(f"{FAMILY_LABEL[fam]} — Cap sweep (TOTAL, 2021-2026 OOS)")
    st.pyplot(fig, clear_figure=True)

    # Table
    show_df = cap_df.copy()
    show_df["sharpe"] = show_df["sharpe"].round(2)
    show_df["sortino"] = show_df["sortino"].round(2)
    show_df["max_dd"] = show_df["max_dd"].round(2)
    show_df["calmar"] = show_df["calmar"].round(2)
    show_df["total_pnl"] = show_df["total_pnl"].round(2)
    show_df["win_day"] = show_df["win_day"].round(1)
    show_df["n_eff"] = show_df["n_eff"].round(2)
    st.dataframe(show_df, use_container_width=True, hide_index=True)

st.divider()

# ── SECTION 2: MPT picker for chosen cap ─────────────────────────
st.header("2. MPT portfolio for selected cap")
st.caption(f"Choose a cap; backend runs MPT on {FAMILY_LABEL[fam]} universe and shows resulting picks.")

cap_choice = st.slider("Cap", min_value=2,
                         max_value=max(len(diff_list), 5),
                         value=5)

with st.spinner(f"Running MPT picker for cap={cap_choice}..."):
    result = run_picker_for_cap(fam, cap_choice)

if result["weights_df"].empty:
    st.warning("Picker returned no results.")
else:
    # Filter to chosen year
    w_year = result["weights_df"][result["weights_df"]["Y_OOS"] == oos_year]
    if w_year.empty:
        st.info(f"No picks for Y{oos_year}.")
    else:
        w_year = w_year.sort_values("weight", ascending=False)
        n_eff = 1.0 / (w_year["weight"] ** 2).sum()

        # Metric strip
        m_tot = result["metrics_df"][result["metrics_df"]["label"]
                                       == f"{fam}_TOTAL"].iloc[0]
        m_yr = result["metrics_df"][result["metrics_df"]["label"]
                                       == f"{fam}_Y{oos_year}"]

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        with mc1:
            st.metric("Picks", len(w_year))
        with mc2:
            st.metric("N_eff", f"{n_eff:.2f}")
        with mc3:
            st.metric("TOTAL Sharpe", f"{m_tot['sharpe']:.2f}")
        with mc4:
            st.metric("TOTAL Max DD", f"{m_tot['max_drawdown']:.2f}")
        with mc5:
            if not m_yr.empty:
                st.metric(f"Y{oos_year} P&L",
                           f"{m_yr.iloc[0]['total_pnl']:+.2f}")

        # Pick table
        display_df = w_year[["diff", "shape", "weight", "cell"]].copy()
        display_df["weight"] = (display_df["weight"] * 100).round(2).astype(str) + "%"
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Per-year metrics
        st.subheader("Per-year metrics")
        m_disp = result["metrics_df"].copy()
        m_disp = m_disp[m_disp["label"] != f"{fam}_TOTAL"]
        m_disp["Year"] = m_disp["label"].str.replace(f"{fam}_Y", "")
        keep_cols = ["Year", "n_days", "total_pnl", "sharpe", "sortino",
                      "max_drawdown", "calmar", "win_day_pct"]
        m_disp = m_disp[keep_cols].round(3)
        st.dataframe(m_disp, use_container_width=True, hide_index=True)

st.divider()

# ── SECTION 3: Custom multiselect ────────────────────────────────
st.header("3. Custom portfolio builder")
st.caption("Pick top-1 cells per diff for Y" + str(oos_year)
            + ". MPT rebalances the weights on selected subset.")

if fam_univ.empty:
    st.info("No candidates in universe for this family/year.")
else:
    # Show top-1 per diff
    top1_per_diff = (fam_univ.sort_values("P_winner", ascending=False)
                              .groupby("diff").head(1)
                              .sort_values("diff")
                              .reset_index(drop=True))
    options = top1_per_diff["diff"].tolist()

    chosen = st.multiselect(
        f"Select diffs to include (top-1 cell per diff, Y{oos_year}):",
        options=options,
        default=options[: min(5, len(options))],
    )
    if not chosen:
        st.info("Select at least 2 diffs to run MPT.")
    elif len(chosen) < 2:
        st.warning("Need at least 2 selections for MPT.")
    else:
        chosen_rows = top1_per_diff[top1_per_diff["diff"].isin(chosen)]
        st.caption(f"Selected {len(chosen_rows)} cells:")
        st.dataframe(
            chosen_rows[["diff", "shape", "cell"]],
            use_container_width=True, hide_index=True,
        )
        st.info(
            "Custom MPT solve on this subset coming in the next iteration. "
            "For now, you can see exactly which cells would be in scope."
        )

st.divider()

# ── Footer ───────────────────────────────────────────────────────
st.caption(
    "Data source: `portfolio_MPT_perfamily_cap5_all.xlsx` + "
    "`top1_picks_per_year_v2.xlsx` + MPT cache at `analytics/mpt_cache/`."
)
