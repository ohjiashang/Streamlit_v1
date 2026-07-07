"""Permutations backtest viewer — interactive parameter explorer.

Formulas available:
  - M212 box (default):    (SGO[2]-SGO[3]) - (ICEGO[1]-ICEGO[2]) - (TC5[2]-TC5[3])
  - M121 outright (best):  SGO[1] - ICEGO[2] - TC5[1]

Sidebar lets you toggle:
  - formula (M212 box / M121 outright)
  - rolling window
  - entry sigma
  - stop-loss mode
"""
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(layout="wide")

BASE = Path(r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\BloombergCOT\analytics")

# Default SL/TP folder map (M-family trades). Per-formula overrides via cfg["sl_dirs"].
SL_DIRS = {
    "None":                   None,  # use formula's nostop_dir
    "SL=1σ_entry, TP=median": BASE / "output_sandbox_perm_sl1_tpmed",
    "SL=2σ_entry, TP=median": BASE / "output_sandbox_perm_sl2_tpmed",
    "SL=3σ_entry, TP=median": BASE / "output_sandbox_perm_sl3_tpmed",
}
SL_DIRS_GN_PLUS = {
    "None":                   BASE / "output_sandbox_gn_plus_perm" / "NoStop",
    "SL=1σ_entry, TP=median": BASE / "output_sandbox_gn_plus_perm" / "SL1",
    "SL=2σ_entry, TP=median": BASE / "output_sandbox_gn_plus_perm" / "SL2",
    "SL=3σ_entry, TP=median": BASE / "output_sandbox_gn_plus_perm" / "SL3",
}
SL_DIRS_GNP2333_SLOPE10 = {
    "None":                   BASE / "output_sandbox_gnp2333_slope10" / "NoStop",
    "SL=1σ_entry, TP=median": BASE / "output_sandbox_gnp2333_slope10" / "SL1",
    "SL=2σ_entry, TP=median": BASE / "output_sandbox_gnp2333_slope10" / "SL2",
    "SL=3σ_entry, TP=median": BASE / "output_sandbox_gnp2333_slope10" / "SL3",
}
SL_DIRS_GN_PLUS_BOX = {
    "None":                   BASE / "output_sandbox_gn_plus_box_perm" / "NoStop",
    "SL=1σ_entry, TP=median": BASE / "output_sandbox_gn_plus_box_perm" / "SL1",
    "SL=2σ_entry, TP=median": BASE / "output_sandbox_gn_plus_box_perm" / "SL2",
    "SL=3σ_entry, TP=median": BASE / "output_sandbox_gn_plus_box_perm" / "SL3",
}
SL_DIRS_GNM1313 = {
    "None":                   BASE / "output_sandbox_unified_gnm1313" / "NoStop",
    "SL=1σ_entry, TP=median": BASE / "output_sandbox_unified_gnm1313" / "SL1",
    "SL=2σ_entry, TP=median": BASE / "output_sandbox_unified_gnm1313" / "SL2",
    "SL=3σ_entry, TP=median": BASE / "output_sandbox_unified_gnm1313" / "SL3",
}
SL_MODES = list(SL_DIRS.keys())
SLTP_SUPPORTED_SIGMAS  = {1.0, 2.0, 3.0}      # SL/TP sweep covers these only
SLTP_SUPPORTED_WINDOWS = {3, 6, 12}

# Hide weekends on all date-axis charts (gas/oil products don't trade Sat/Sun).
RANGEBREAKS = [dict(bounds=["sat", "mon"])]

# Formula registry: each formula has a label, scenario-name prefix, series dir,
# and supported (window, sigma) grid. Trades dirs are shared across formulas.
def _outright(label, prefix, formula_str):
    return label, {
        "prefix":     prefix,
        "formula_str": formula_str,
        "series_dir": BASE / "output_sandbox_permutations_sweep",
        "nostop_dir": BASE / "output_sandbox_permutations_sweep",
        "windows":    [3, 6, 12],
        "sigmas":     [1.0, 2.0, 3.0],
    }

def _box(label, prefix, formula_str):
    return label, {
        "prefix":     prefix,
        "formula_str": formula_str,
        "series_dir": BASE / "output_sandbox_permutations_sweep",
        "nostop_dir": BASE / "output_sandbox_permutations_sweep",
        "windows":    [3, 6, 12],
        "sigmas":     [1.0, 2.0, 3.0],
    }

FORMULAS = dict([
    ("M212 box", {
        "prefix":     "M212box",
        "formula_str": "(SGO[2]−SGO[3]) − (ICEGO[1]−ICEGO[2]) − (TC5[2]−TC5[3])",
        "series_dir": BASE / "output_sandbox_m212box_sweep",
        "nostop_dir": BASE / "output_sandbox_m212box_sweep",
        "windows":    [1, 3, 6, 12],
        "sigmas":     [1.0, 1.5, 2.0, 2.5, 3.0],
    }),
    _box(     "M333 box",     "M333box", "(SGO[3]−SGO[4]) − (ICEGO[3]−ICEGO[4]) − (TC5[3]−TC5[4])"),
    _outright("M232 outright", "M232",    "SGO[2] − ICEGO[3] − TC5[2]"),
    ("G+N M2333", {
        "prefix":      "GNp2333",
        "formula_str": "SGO[2] − ICEGO[3] + NJC[3] − NEC[3]",
        "series_dir":  BASE / "output_sandbox_gn_plus_perm" / "NoStop",
        "nostop_dir":  BASE / "output_sandbox_gn_plus_perm" / "NoStop",
        "windows":     [3, 6, 12],
        "sigmas":      [1.0, 2.0, 3.0],
        "sl_dirs":     SL_DIRS_GN_PLUS,
    }),
    ("G+N M2333 + slope-10 filter", {
        "prefix":      "GNp2333",
        "formula_str": "SGO[2] − ICEGO[3] + NJC[3] − NEC[3]   (slope-10 filtered entries)",
        # Series data is identical to baseline — reuse it
        "series_dir":  BASE / "output_sandbox_gn_plus_perm" / "NoStop",
        # Trades come from the slope-10 filtered backtest
        "nostop_dir":  BASE / "output_sandbox_gnp2333_slope10" / "NoStop",
        "windows":     [3, 6, 12],
        "sigmas":      [1.0, 2.0, 3.0],
        "sl_dirs":     SL_DIRS_GNP2333_SLOPE10,
    }),
    ("G+N box 3332 (W6M σ2.0)", {
        "prefix":      "GNp3332box",
        "formula_str": "(SGO[3]−SGO[4]) − (ICEGO[3]−ICEGO[4]) + (NJC[3]−NJC[4]) − (NEC[2]−NEC[3])",
        "series_dir":  BASE / "output_sandbox_gn_plus_box_perm" / "NoStop",
        "nostop_dir":  BASE / "output_sandbox_gn_plus_box_perm" / "NoStop",
        "windows":     [6],
        "sigmas":      [2.0],
        "sl_dirs":     SL_DIRS_GN_PLUS_BOX,
    }),
    ("GNM1313 (W6M σ1.0) — v3 anchor pick", {
        "prefix":      "GNM1313",
        "formula_str": "SGO[1] − ICEGO[3] + NJC[1] − NEC[3]",
        "series_dir":  BASE / "output_sandbox_unified_gnm1313" / "NoStop",
        "nostop_dir":  BASE / "output_sandbox_unified_gnm1313" / "NoStop",
        "windows":     [6],
        "sigmas":      [1.0],
        "sl_dirs":     SL_DIRS_GNM1313,
    }),
])

@st.cache_data(ttl=300)
def compute_overview_grid(formula_label: str) -> pd.DataFrame:
    """For the selected formula, compute key metrics across all (W, σ, SL) combos."""
    cfg = FORMULAS[formula_label]
    rows = []
    for w in cfg["windows"]:
        for s in cfg["sigmas"]:
            for sl_mode in SL_MODES:
                if sl_mode != "None":
                    if w not in SLTP_SUPPORTED_WINDOWS or s not in SLTP_SUPPORTED_SIGMAS:
                        continue
                sl_dirs = cfg.get("sl_dirs") or SL_DIRS
                tdir = cfg["nostop_dir"] if sl_mode == "None" else sl_dirs[sl_mode]
                cell_name = f"{cfg['prefix']}_W{w}M_S{s}sd"
                fp = tdir / cell_name / "trades.xlsx"
                if not fp.exists():
                    continue
                t = pd.read_excel(fp)
                if t.empty:
                    continue
                n        = len(t)
                pnl_sum  = float(t["pnl"].sum())
                ml_sum   = float(t["max_loss"].sum())
                ratio    = pnl_sum / -ml_sum if ml_sum < 0 else np.nan
                wr       = float((t["pnl"] > 0).mean() * 100)
                avg, sd_ = float(t["pnl"].mean()), float(t["pnl"].std())
                inv_cv   = avg / sd_ if sd_ else np.nan
                longest  = int(t["bd_underwater"].max())  if "bd_underwater" in t else None
                median_u = float(t["bd_underwater"].median()) if "bd_underwater" in t else None
                pct_stop = float((t["exit_reason"] == "stop").mean() * 100) if "exit_reason" in t else None
                rows.append({
                    "window": w, "sigma": s, "sl_mode": sl_mode,
                    "trades": n, "pnl": pnl_sum, "ratio": ratio,
                    "win": wr, "inv_cv": inv_cv,
                    "longest_uw": longest, "median_uw": median_u,
                    "pct_stop": pct_stop,
                })
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def load_scenario(formula_label: str, window: int, sigma: float, sl_mode: str):
    cfg = FORMULAS[formula_label]
    name = f"{cfg['prefix']}_W{window}M_S{sigma}sd"
    series = pd.read_parquet(cfg["series_dir"] / name / "series.parquet")
    series["Date"] = pd.to_datetime(series["Date"])

    # Live-tail display: contiguous trailing days where the scaled-roll blend is
    # active (blend_weight_new > 0) get shown as raw box on the chunk's anchor
    # contracts, not the blended value. Historical blend windows stay blended so
    # rolling stats/bands remain consistent.
    series["EW_adj_display"] = series["EW_adj"]
    if "EW_raw" in series.columns:
        bw = series["blend_weight_new"].fillna(0.0).values
        n_tail = 0
        for v in bw[::-1]:
            if v > 0:
                n_tail += 1
            else:
                break
        if n_tail > 0:
            idx = series.index[-n_tail:]
            series.loc[idx, "EW_adj_display"] = (
                series.loc[idx, "EW_raw"] - series.loc[idx, "norm_value"]
            )

    sl_dirs = cfg.get("sl_dirs") or SL_DIRS
    trades_dir = cfg["nostop_dir"] if sl_mode == "None" else sl_dirs[sl_mode]
    trades = pd.read_excel(trades_dir / name / "trades.xlsx")
    trades["entry_date"] = pd.to_datetime(trades["entry_date"])
    trades["exit_date"]  = pd.to_datetime(trades["exit_date"])
    trades["year"]       = trades["entry_date"].dt.year

    # Reconstruct pnl_running from trades (no-stop M212box has it baked into parquet,
    # but for any other case we rebuild it consistently).
    if sl_mode != "None" or formula_label != "M212 box":
        cum = trades.sort_values("exit_date").reset_index(drop=True)
        cum["cum_pnl"] = cum["pnl"].cumsum()
        series = series.drop(columns=["pnl_running"], errors="ignore").merge(
            cum[["exit_date", "cum_pnl"]].rename(columns={"exit_date": "Date"}),
            on="Date", how="left"
        )
        series["pnl_running"] = series["cum_pnl"].ffill().fillna(0.0)
        series = series.drop(columns=["cum_pnl"])

    return name, series, trades


def yearly_stats(trades: pd.DataFrame, has_stops: bool) -> pd.DataFrame:
    aggs = {
        "n":        ("pnl", "size"),
        "pnl":      ("pnl", "sum"),
        "max_loss": ("max_loss", "sum"),
        "avg_pnl":  ("pnl", "mean"),
        "sd_pnl":   ("pnl", "std"),
        "win":      ("pnl", lambda x: (x > 0).mean() * 100),
    }
    if has_stops:
        aggs["pct_stop"] = ("exit_reason", lambda x: (x == "stop").mean() * 100)
    g = trades.groupby("year").agg(**aggs)
    g["ratio"] = g["pnl"] / -g["max_loss"]
    g["inv_cv_ratio"] = g["avg_pnl"] / g["sd_pnl"]  # signal-to-noise; higher = better
    total_row = {
        "n":            len(trades),
        "pnl":          trades["pnl"].sum(),
        "max_loss":     trades["max_loss"].sum(),
        "avg_pnl":      trades["pnl"].mean(),
        "sd_pnl":       trades["pnl"].std(),
        "win":          (trades["pnl"] > 0).mean() * 100,
        "ratio":        (trades["pnl"].sum() / -trades["max_loss"].sum()
                         if trades["max_loss"].sum() < 0 else np.nan),
        "inv_cv_ratio": (trades["pnl"].mean() / trades["pnl"].std()
                         if trades["pnl"].std() else np.nan),
    }
    if has_stops:
        total_row["pct_stop"] = (trades["exit_reason"] == "stop").mean() * 100
    return pd.concat([g, pd.DataFrame(total_row, index=["TOTAL"])])


# ── Sidebar ────────────────────────────────────────────────────────
st.sidebar.header("Strategy parameters")
formula_label = st.sidebar.radio("Formula", list(FORMULAS.keys()), index=0)
cfg = FORMULAS[formula_label]
windows_avail = cfg["windows"]
sigmas_avail  = cfg["sigmas"]
default_w = 6 if 6 in windows_avail else windows_avail[len(windows_avail)//2]
default_s = 3.0 if 3.0 in sigmas_avail else sigmas_avail[-1]

window  = st.sidebar.selectbox("Rolling window (months)", windows_avail,
                                index=windows_avail.index(default_w))
sigma   = st.sidebar.selectbox("Entry sigma", sigmas_avail,
                                index=sigmas_avail.index(default_s))
sl_mode = st.sidebar.radio("Stop loss", SL_MODES, index=0)
show_slope10 = st.sidebar.checkbox("Overlay slope-10 indicator", value=False,
                                    help="Adds a panel below the main series showing 10-day rolling slope of EW_adj, with entry markers")

# Guard: SL/TP sweep only covers a subset of (window, sigma)
if sl_mode != "None":
    if window not in SLTP_SUPPORTED_WINDOWS or sigma not in SLTP_SUPPORTED_SIGMAS:
        st.warning(f"SL/TP results only available for windows ∈ {sorted(SLTP_SUPPORTED_WINDOWS)} "
                   f"and sigmas ∈ {sorted(SLTP_SUPPORTED_SIGMAS)}. "
                   f"Showing no-stop results instead.")
        sl_mode = "None"

name, series, trades = load_scenario(formula_label, window, sigma, sl_mode)
has_stops = sl_mode != "None"

# ── Header / top metrics ───────────────────────────────────────────
st.title("Backtest viewer")
st.caption(f"**{formula_label}** — `{cfg['formula_str']}`  |  scaled-roll blending (5 BD)")

# ── Performance overview matrix ────────────────────────────────────
with st.container():
    st.subheader("Performance overview — all (window, σ, stop) combos")
    grid = compute_overview_grid(formula_label)
    METRIC_DEFS = {
        "Return ($/bbl)":   ("pnl",        True,  "{:+.2f}"),
        "Ratio":            ("ratio",      True,  "{:.2f}"),
        "Win %":            ("win",        True,  "{:.0f}%"),
        "Inv CV (avg/sd)":  ("inv_cv",     True,  "{:.2f}"),
        "Longest UW (BD)":  ("longest_uw", False, "{:.0f}"),
        "Median UW (BD)":   ("median_uw",  False, "{:.1f}"),
    }
    chosen = st.selectbox("Color cells by", list(METRIC_DEFS.keys()), index=0)
    col, higher_better, fmt = METRIC_DEFS[chosen]

    # Pivot: rows = (W, σ), cols = SL mode, values = chosen metric
    grid["wsigma"] = grid.apply(lambda r: f"W{int(r['window'])}M_S{r['sigma']}sd", axis=1)
    piv = grid.pivot(index="wsigma", columns="sl_mode", values=col)
    # Reorder by window then sigma
    piv = piv.reindex([f"W{w}M_S{s}sd" for w in cfg["windows"] for s in cfg["sigmas"]])
    # Reorder SL columns: None → SL=3σ → SL=2σ → SL=1σ (tightest stop on the right)
    HEATMAP_ORDER = ["None",
                     "SL=3σ_entry, TP=median",
                     "SL=2σ_entry, TP=median",
                     "SL=1σ_entry, TP=median"]
    piv = piv.reindex(columns=[m for m in HEATMAP_ORDER if m in piv.columns])

    # Heatmap (Plotly)
    z_vals = piv.values
    text_vals = [[fmt.format(v) if pd.notna(v) else "—" for v in row] for row in z_vals]
    colorscale = "RdYlGn" if higher_better else "RdYlGn_r"
    heat = go.Figure(go.Heatmap(
        z=z_vals,
        x=list(piv.columns),
        y=list(piv.index),
        text=text_vals,
        texttemplate="%{text}",
        textfont=dict(size=11),
        colorscale=colorscale,
        zmid=None,
        showscale=True,
        hoverongaps=False,
        colorbar=dict(title=chosen),
    ))
    heat.update_layout(height=420, margin=dict(l=30, r=20, t=20, b=40),
                       xaxis_title="Stop-loss mode", yaxis_title="Window × σ")
    st.plotly_chart(heat, use_container_width=True)

    # Best-of summary
    def best_of(g: pd.DataFrame, col: str, ascending: bool, fmt: str):
        sub = g.dropna(subset=[col])
        if sub.empty:
            return ("—", "—")
        idx = sub[col].idxmin() if ascending else sub[col].idxmax()
        best = sub.loc[idx]
        label = f"W{int(best['window'])}M_S{best['sigma']}sd · {best['sl_mode']}"
        return (label, fmt.format(best[col]))

    bc1, bc2, bc3, bc4 = st.columns(4)
    lbl, val = best_of(grid, "pnl",        ascending=False, fmt="${:+.2f}")
    bc1.metric(f"Best Return  ({val})",     lbl)
    lbl, val = best_of(grid, "ratio",      ascending=False, fmt="{:.2f}")
    bc2.metric(f"Best Ratio  ({val})",      lbl)
    lbl, val = best_of(grid, "win",        ascending=False, fmt="{:.0f}%")
    bc3.metric(f"Best Win %  ({val})",      lbl)
    lbl, val = best_of(grid, "longest_uw", ascending=True,  fmt="{:.0f} BD")
    bc4.metric(f"Lowest longest UW  ({val})", lbl)

st.markdown("---")
st.subheader(f"Drilldown — `{name}` · {sl_mode}")

total_pnl  = trades["pnl"].sum()
total_ml   = trades["max_loss"].sum()
ratio      = total_pnl / -total_ml if total_ml < 0 else float("inf")
winrate    = (trades["pnl"] > 0).mean() * 100
hold       = trades["holding_bd"].mean()
avg_pnl    = trades["pnl"].mean()
sd_pnl     = trades["pnl"].std()
inv_cv_rt  = avg_pnl / sd_pnl if sd_pnl else float("nan")  # signal-to-noise
last       = series.iloc[-1]
pct_stop   = (trades["exit_reason"] == "stop").mean() * 100 if has_stops else None

if has_stops:
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
else:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Trades", f"{len(trades)}")
c2.metric("Total P&L ($/bbl)", f"{total_pnl:+.2f}")
c3.metric("Ratio", f"{ratio:.2f}")
c4.metric("Inv CV (avg/sd)", f"{inv_cv_rt:.2f}")
c5.metric("Win rate", f"{winrate:.1f}%")
c6.metric("Avg hold (BD)", f"{hold:.0f}")
if has_stops:
    c7.metric("% stopped", f"{pct_stop:.0f}%")

st.markdown(f"**Scenario:** `{name}`  |  range: {series['Date'].min().date()} → {series['Date'].max().date()}  "
            f"({len(series):,} obs)  |  **Stop mode:** {sl_mode}")
last_raw_tail = bool(last["blend_weight_new"] and last["blend_weight_new"] > 0 and "EW_raw" in series.columns)
last_display = last["EW_adj_display"]
last_lbl = "EW_adj (raw, anchor contracts)" if last_raw_tail else "EW_adj"
st.markdown(f"**Current state ({last['Date'].date()}, contracts {last['contract']})**: "
            f"{last_lbl} = {last_display:+.3f}  |  "
            f"median = {last['rolling_median']:+.3f}  |  band = [{last['lower_bound']:+.3f}, {last['upper_bound']:+.3f}]")

# ── Full series ────────────────────────────────────────────────────
band_cd = series[["rolling_std", "rolling_median"]].values
med_cd  = series[["rolling_std"]].values
ew_cd   = series[["rolling_median", "rolling_std"]].values

fig = go.Figure()
fig.add_trace(go.Scatter(x=series["Date"], y=series["upper_bound"],
                         line=dict(color="rgba(0,0,0,0)"), showlegend=False, name="Upper",
                         customdata=band_cd,
                         hovertemplate="<b>%{x|%Y-%m-%d}</b><br>"
                                       f"Upper +{sigma}σ: %{{y:.3f}}<br>"
                                       "1σ: %{customdata[0]:.3f}<br>"
                                       "Median: %{customdata[1]:.3f}<extra></extra>"))
fig.add_trace(go.Scatter(x=series["Date"], y=series["lower_bound"],
                         line=dict(color="rgba(0,0,0,0)"), fill="tonexty",
                         fillcolor="rgba(120,170,210,0.30)", name=f"±{sigma}σ band",
                         customdata=band_cd,
                         hovertemplate="<b>%{x|%Y-%m-%d}</b><br>"
                                       f"Lower −{sigma}σ: %{{y:.3f}}<br>"
                                       "1σ: %{customdata[0]:.3f}<br>"
                                       "Median: %{customdata[1]:.3f}<extra></extra>"))
fig.add_trace(go.Scatter(x=series["Date"], y=series["rolling_median"],
                         line=dict(color="grey", width=1.4), name=f"{window}m median",
                         customdata=med_cd,
                         hovertemplate="<b>%{x|%Y-%m-%d}</b><br>"
                                       "Median: %{y:.3f}<br>"
                                       "1σ: %{customdata[0]:.3f}<extra></extra>"))
fig.add_trace(go.Scatter(x=series["Date"], y=series["EW_adj_display"],
                         line=dict(color="black", width=1.1), name="EW_adj",
                         customdata=ew_cd,
                         hovertemplate="<b>%{x|%Y-%m-%d}</b><br>"
                                       "EW: %{y:.3f}<br>"
                                       "Median: %{customdata[0]:.3f}<br>"
                                       "1σ: %{customdata[1]:.3f}<extra></extra>"))
# Mark live-tail rows shown as raw (anchor contracts) so user can spot them
raw_tail = series[series["EW_adj_display"] != series["EW_adj"]]
if not raw_tail.empty:
    fig.add_trace(go.Scatter(
        x=raw_tail["Date"], y=raw_tail["EW_adj_display"],
        mode="markers",
        marker=dict(color="orange", size=7, symbol="circle-open",
                    line=dict(color="orange", width=2)),
        name=f"Raw (anchor contracts, last {len(raw_tail)} BD)",
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>EW raw (anchor): %{y:.3f}<extra></extra>",
    ))
L = trades[trades["side"] == "long"]
S = trades[trades["side"] == "short"]
fig.add_trace(go.Scatter(x=L["entry_date"], y=L["entry"], mode="markers",
                         marker=dict(symbol="triangle-up", color="darkgreen", size=10, line=dict(color="black", width=0.5)),
                         name=f"Long entry ({len(L)})"))
fig.add_trace(go.Scatter(x=S["entry_date"], y=S["entry"], mode="markers",
                         marker=dict(symbol="triangle-down", color="darkred", size=10, line=dict(color="black", width=0.5)),
                         name=f"Short entry ({len(S)})"))

if has_stops:
    med_exits  = trades[trades["exit_reason"] == "median"]
    stop_exits = trades[trades["exit_reason"] == "stop"]
    fig.add_trace(go.Scatter(x=med_exits["exit_date"], y=med_exits["exit"], mode="markers",
                             marker=dict(symbol="x", color="black", size=8),
                             name=f"Median exit ({len(med_exits)})"))
    fig.add_trace(go.Scatter(x=stop_exits["exit_date"], y=stop_exits["exit"], mode="markers",
                             marker=dict(symbol="x", color="red", size=11, line=dict(color="black", width=1.0)),
                             name=f"Stop ({len(stop_exits)})"))
else:
    fig.add_trace(go.Scatter(x=trades["exit_date"], y=trades["exit"], mode="markers",
                             marker=dict(symbol="x", color="black", size=8),
                             name="Exit"))

fig.update_layout(height=420, margin=dict(l=40, r=20, t=30, b=30),
                  title=f"Full series — {window}m / {sigma}σ  |  {sl_mode}",
                  yaxis_title="$/bbl (back-adj)", legend=dict(orientation="h", y=-0.15))
fig.update_xaxes(rangebreaks=RANGEBREAKS)
main_event = st.plotly_chart(fig, use_container_width=True,
                             on_select="rerun", selection_mode="points",
                             key=f"main_chart_{name}_{sl_mode}")

# ── Click-to-zoom on entry markers ─────────────────────────────────
trades_sorted = trades.sort_values("entry_date").reset_index(drop=True)
clicked_idx = None
if main_event and getattr(main_event, "selection", None):
    pts = main_event.selection.get("points") if isinstance(main_event.selection, dict) else main_event.selection.points
    if pts:
        clicked_x = pts[0].get("x")
        if clicked_x is not None:
            clicked_date = pd.to_datetime(clicked_x).normalize()
            m = trades_sorted[trades_sorted["entry_date"].dt.normalize() == clicked_date]
            if not m.empty:
                clicked_idx = int(m.index[0])

st.markdown("**Zoom into a trade entry** — click an entry triangle on the chart above, or pick from the dropdown.")
labels = [f"#{i:>3}  {r['entry_date'].date()}  {r['side']:<5}  entry={r['entry']:+.3f}  pnl=${r['pnl']:+.2f}"
          for i, r in trades_sorted.iterrows()]
default_label_idx = clicked_idx if clicked_idx is not None else 0
chosen_label = st.selectbox("Trade", labels, index=default_label_idx,
                             key=f"trade_picker_{name}_{sl_mode}")
chosen_idx = labels.index(chosen_label)
trade = trades_sorted.iloc[chosen_idx]

entry_date = trade["entry_date"]
exit_date  = trade["exit_date"]
dates_arr  = series["Date"].values
entry_pos  = int(np.searchsorted(dates_arr, np.datetime64(entry_date)))
exit_pos   = int(np.searchsorted(dates_arr, np.datetime64(exit_date)))
PAD_PRE, PAD_POST = 20, 10
lo = max(0, entry_pos - PAD_PRE)
hi = min(len(series), exit_pos + PAD_POST + 1)
zoom = series.iloc[lo:hi]

SLOPE_W = 10
fit_lo  = max(0, entry_pos - SLOPE_W + 1)
fit_win = series.iloc[fit_lo:entry_pos + 1]
y_fit   = fit_win["EW_adj"].values
x_fit   = np.arange(len(y_fit), dtype=float)
slope_val, intercept = np.polyfit(x_fit, y_fit, 1) if len(y_fit) >= 2 else (np.nan, np.nan)
y_line  = slope_val * x_fit + intercept if len(y_fit) >= 2 else y_fit
sigma_at_entry = float(fit_win["rolling_std"].iloc[-1]) if not fit_win.empty else float("nan")
k_norm  = slope_val / sigma_at_entry if sigma_at_entry else float("nan")

fig_z = go.Figure()
fig_z.add_trace(go.Scatter(x=zoom["Date"], y=zoom["upper_bound"],
                           line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip"))
fig_z.add_trace(go.Scatter(x=zoom["Date"], y=zoom["lower_bound"],
                           line=dict(color="rgba(0,0,0,0)"), fill="tonexty",
                           fillcolor="rgba(120,170,210,0.30)", name=f"±{sigma}σ band", hoverinfo="skip"))
fig_z.add_trace(go.Scatter(x=zoom["Date"], y=zoom["rolling_median"],
                           line=dict(color="grey", width=1.2), name=f"{window}m median"))
fig_z.add_trace(go.Scatter(x=zoom["Date"], y=zoom["EW_adj"],
                           line=dict(color="black", width=1.4), name="EW_adj"))
fig_z.add_trace(go.Scatter(x=fit_win["Date"], y=y_line,
                           line=dict(color="orange", width=2.4),
                           name=f"10-BD best fit (slope={slope_val:+.4f}, slope/σ={k_norm:+.2f})"))

side = trade["side"]
sym  = "triangle-up" if side == "long" else "triangle-down"
col  = "darkgreen"   if side == "long" else "darkred"
fig_z.add_trace(go.Scatter(x=[entry_date], y=[trade["entry"]], mode="markers",
                           marker=dict(symbol=sym, color=col, size=16, line=dict(color="black", width=1)),
                           name=f"{side} entry"))
exit_reason = trade.get("exit_reason", "exit")
exit_sym_col = ("red", 14) if exit_reason == "stop" else ("black", 11)
fig_z.add_trace(go.Scatter(x=[exit_date], y=[trade["exit"]], mode="markers",
                           marker=dict(symbol="x", color=exit_sym_col[0], size=exit_sym_col[1],
                                        line=dict(color="black", width=1)),
                           name=f"exit ({exit_reason})"))

hold_bd = int(trade.get("holding_bd", 0))
fig_z.update_layout(height=380, margin=dict(l=40, r=20, t=40, b=30),
                    title=f"Zoom — trade #{chosen_idx} · {side} entry {entry_date.date()} → "
                          f"{exit_reason} {exit_date.date()} ({hold_bd} BD)  ·  pnl=${trade['pnl']:+.2f}",
                    yaxis_title="$/bbl", legend=dict(orientation="h", y=-0.18))
fig_z.update_xaxes(rangebreaks=RANGEBREAKS)
st.plotly_chart(fig_z, use_container_width=True)

# ── Slope-10 overlay panel (optional) ──────────────────────────────
if show_slope10:
    SLOPE_W = 10
    SLOPE_K = 0.3
    x = np.arange(SLOPE_W, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    def _fit(y):
        return ((x - x_mean) * (y - y.mean())).sum() / x_var
    slope10 = series["EW_adj"].rolling(SLOPE_W, min_periods=SLOPE_W).apply(_fit, raw=True)
    thresh_pos = SLOPE_K * series["rolling_std"]
    thresh_neg = -SLOPE_K * series["rolling_std"]

    # Map entry dates → slope value on that date (left-join via index)
    series_slope = pd.DataFrame({"Date": series["Date"], "slope": slope10.values})
    L_slope = L.merge(series_slope, left_on="entry_date", right_on="Date", how="left")
    S_slope = S.merge(series_slope, left_on="entry_date", right_on="Date", how="left")

    fig_sl = go.Figure()
    # ±K·σ adaptive threshold band
    fig_sl.add_trace(go.Scatter(x=series["Date"], y=thresh_pos,
                                line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip"))
    fig_sl.add_trace(go.Scatter(x=series["Date"], y=thresh_neg,
                                line=dict(color="rgba(0,0,0,0)"), fill="tonexty",
                                fillcolor="rgba(180,180,180,0.25)",
                                name=f"±{SLOPE_K}·σ band", hoverinfo="skip"))
    fig_sl.add_trace(go.Scatter(x=series["Date"], y=slope10,
                                line=dict(color="steelblue", width=1.1),
                                name="slope-10",
                                hovertemplate="<b>%{x|%Y-%m-%d}</b><br>slope: %{y:.4f}<extra></extra>"))
    fig_sl.add_hline(y=0, line_color="grey", line_width=0.7)
    if not L_slope.empty:
        fig_sl.add_trace(go.Scatter(x=L_slope["entry_date"], y=L_slope["slope"], mode="markers",
                                    marker=dict(symbol="triangle-up", color="darkgreen", size=10,
                                                line=dict(color="black", width=0.5)),
                                    name=f"Long entry ({len(L_slope)})",
                                    hovertemplate="<b>%{x|%Y-%m-%d}</b><br>slope: %{y:.4f}<extra></extra>"))
    if not S_slope.empty:
        fig_sl.add_trace(go.Scatter(x=S_slope["entry_date"], y=S_slope["slope"], mode="markers",
                                    marker=dict(symbol="triangle-down", color="darkred", size=10,
                                                line=dict(color="black", width=0.5)),
                                    name=f"Short entry ({len(S_slope)})",
                                    hovertemplate="<b>%{x|%Y-%m-%d}</b><br>slope: %{y:.4f}<extra></extra>"))
    fig_sl.update_layout(height=260, margin=dict(l=40, r=20, t=30, b=30),
                         title=f"10-day rolling slope of EW_adj  |  filter passes when long: slope ≥ +{SLOPE_K}·σ, short: slope ≤ −{SLOPE_K}·σ",
                         yaxis_title="slope ($/bbl per BD)",
                         legend=dict(orientation="h", y=-0.2))
    fig_sl.update_xaxes(rangebreaks=RANGEBREAKS)
    st.plotly_chart(fig_sl, use_container_width=True)

# ── Yearly grid (wide form) ────────────────────────────────────────
years = sorted(series["Date"].dt.year.unique())
N_COLS = 6
N_ROWS = int(np.ceil(len(years) / N_COLS))
y_lo = float(series["lower_bound"].min())
y_hi = float(series["upper_bound"].max())

yr_titles = []
yr_pnl = trades.groupby("year")["pnl"].sum().to_dict()
yr_n   = trades.groupby("year")["pnl"].size().to_dict()
yr_stops = (trades[trades["exit_reason"] == "stop"].groupby("year").size().to_dict()
            if has_stops else {})
for yr in years:
    n = yr_n.get(yr, 0); pnl = yr_pnl.get(yr, 0.0); ns = yr_stops.get(yr, 0)
    if has_stops:
        yr_titles.append(f"{yr}  n={n}  ${pnl:+.2f}  stops={ns}")
    else:
        yr_titles.append(f"{yr}  n={n}  ${pnl:+.2f}")

grid = make_subplots(rows=N_ROWS, cols=N_COLS, shared_yaxes=True,
                     subplot_titles=yr_titles, horizontal_spacing=0.015, vertical_spacing=0.12)
for i, yr in enumerate(years):
    r = i // N_COLS + 1
    c = i %  N_COLS + 1
    s = series[series["Date"].dt.year == yr]
    grid.add_trace(go.Scatter(x=s["Date"], y=s["upper_bound"], line=dict(color="rgba(0,0,0,0)"),
                              showlegend=False, hoverinfo="skip"), row=r, col=c)
    grid.add_trace(go.Scatter(x=s["Date"], y=s["lower_bound"], line=dict(color="rgba(0,0,0,0)"),
                              fill="tonexty", fillcolor="rgba(120,170,210,0.25)",
                              showlegend=False, hoverinfo="skip"), row=r, col=c)
    grid.add_trace(go.Scatter(x=s["Date"], y=s["rolling_median"], line=dict(color="grey", width=0.9),
                              showlegend=False, hoverinfo="skip"), row=r, col=c)
    grid.add_trace(go.Scatter(x=s["Date"], y=s["EW_adj"], line=dict(color="black", width=0.9),
                              showlegend=False, hoverinfo="skip"), row=r, col=c)
    tr = trades[trades["year"] == yr]
    if not tr.empty:
        tL = tr[tr["side"] == "long"]; tS = tr[tr["side"] == "short"]
        if not tL.empty:
            grid.add_trace(go.Scatter(x=tL["entry_date"], y=tL["entry"], mode="markers",
                                      marker=dict(symbol="triangle-up", color="darkgreen", size=8, line=dict(color="black", width=0.4)),
                                      showlegend=False, hoverinfo="skip"), row=r, col=c)
        if not tS.empty:
            grid.add_trace(go.Scatter(x=tS["entry_date"], y=tS["entry"], mode="markers",
                                      marker=dict(symbol="triangle-down", color="darkred", size=8, line=dict(color="black", width=0.4)),
                                      showlegend=False, hoverinfo="skip"), row=r, col=c)
        if has_stops:
            tm = tr[tr["exit_reason"] == "median"]; ts = tr[tr["exit_reason"] == "stop"]
            grid.add_trace(go.Scatter(x=tm["exit_date"], y=tm["exit"], mode="markers",
                                      marker=dict(symbol="x", color="black", size=6),
                                      showlegend=False, hoverinfo="skip"), row=r, col=c)
            grid.add_trace(go.Scatter(x=ts["exit_date"], y=ts["exit"], mode="markers",
                                      marker=dict(symbol="x", color="red", size=8,
                                                   line=dict(color="black", width=0.8)),
                                      showlegend=False, hoverinfo="skip"), row=r, col=c)
        else:
            grid.add_trace(go.Scatter(x=tr["exit_date"], y=tr["exit"], mode="markers",
                                      marker=dict(symbol="x", color="black", size=6),
                                      showlegend=False, hoverinfo="skip"), row=r, col=c)
    grid.update_yaxes(range=[y_lo, y_hi], row=r, col=c, showgrid=True, gridcolor="rgba(0,0,0,0.08)")
    grid.update_xaxes(row=r, col=c, showgrid=True, gridcolor="rgba(0,0,0,0.08)")

grid.update_layout(height=520, margin=dict(l=30, r=20, t=30, b=20),
                   title=f"Yearly zooms (shared y-axis)  |  {sl_mode}")
grid.update_xaxes(rangebreaks=RANGEBREAKS)
grid.update_annotations(font_size=10)
st.plotly_chart(grid, use_container_width=True)

# ── Cumulative P&L ─────────────────────────────────────────────────
fig = go.Figure()
fig.add_trace(go.Scatter(x=series["Date"], y=series["pnl_running"],
                         line=dict(color="darkblue", width=1.6), name="Cumulative P&L",
                         fill="tozeroy", fillcolor="rgba(0,100,0,0.18)"))
fig.add_hline(y=0, line_color="grey", line_width=0.8)
fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=30),
                  title=f"Cumulative P&L  (${total_pnl:+.2f}/bbl)",
                  yaxis_title="$/bbl")
fig.update_xaxes(rangebreaks=RANGEBREAKS)
st.plotly_chart(fig, use_container_width=True)

# ── Per-trade bars + yearly stats ──────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    fig = go.Figure()
    if has_stops:
        bar_colors = [
            ("darkgreen" if v > 0 else "lightgreen") if r == "median"
            else ("lightcoral" if v > 0 else "darkred")
            for v, r in zip(trades["pnl"], trades["exit_reason"])
        ]
    else:
        bar_colors = ["darkgreen" if v > 0 else "darkred" for v in trades["pnl"]]
    fig.add_trace(go.Bar(x=list(range(len(trades))), y=trades["pnl"],
                         marker_color=bar_colors,
                         marker_line=dict(color="black", width=0.4),
                         showlegend=False))
    fig.add_hline(y=0, line_color="grey", line_width=0.6)
    title_extra = "  (dark = median exit, light/red = stop)" if has_stops else ""
    fig.update_layout(height=360, margin=dict(l=40, r=20, t=30, b=30),
                      title=f"Per-trade P&L{title_extra}", xaxis_title="Trade #", yaxis_title="$/bbl")
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    ys = yearly_stats(trades, has_stops)
    cols_table = {
        "Year":     [str(i) for i in ys.index],
        "N":        ys["n"].astype(int),
        "P&L":      ys["pnl"].map(lambda v: f"${v:+.2f}"),
        "Max Loss": ys["max_loss"].map(lambda v: f"${v:+.2f}"),
        "Ratio":    ys["ratio"].map(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Inv CV":   ys["inv_cv_ratio"].map(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Win":      ys["win"].map(lambda v: f"{v:.0f}%"),
    }
    if has_stops:
        cols_table["Stop%"] = ys["pct_stop"].map(lambda v: f"{v:.0f}%")
    ys_display = pd.DataFrame(cols_table).reset_index(drop=True)
    st.markdown("**Yearly stats**")
    st.dataframe(ys_display, hide_index=True, use_container_width=True, height=420)
