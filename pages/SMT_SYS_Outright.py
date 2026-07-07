"""SMT-SYS Outright viewer — interactive (a,b) explorer.

Formula:  SMT[a] - SYS[b]      where SMT = S380 fuel oil, SYS = S92 gasoline.
9 perms (a,b ∈ {1,2,3}). Series built on the fly via backtest_from_config.
Trades read from analytics/output_sandbox_smt_sys_sweep/SS_outright/<cell>/trades.xlsx.
"""
import sys
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(layout="wide")

ANALYTICS = Path(r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\BloombergCOT\analytics")
sys.path.insert(0, str(ANALYTICS))
import backtest_from_config as bfc

CONFIG = ANALYTICS / "config" / "sandbox_permutations_sweep.xlsx"
SWEEP  = ANALYTICS / "output_sandbox_smt_sys_sweep" / "SS_outright"

WINDOWS  = [3, 6, 12]
SIGMAS_E = [1.0, 2.0, 3.0]
SIGMAS_S = [1.0, 2.0, 3.0]
SLOPE_WS = [0, 5, 10, 15]
MONTHS   = [1, 2, 3]
RANGEBREAKS = [dict(bounds=["sat", "mon"])]


@st.cache_resource
def load_panels():
    bfc.CONFIG_FILE = CONFIG
    legs, _, products_map = bfc.load_config()
    legs["SMT"] = {"leg_name": "SMT", "formula": "SMT", "offset_months": 1}
    legs["SYS"] = {"leg_name": "SYS", "formula": "SYS", "offset_months": 1}
    products_map["SMT"] = "SMT_18m.xlsx"
    products_map["SYS"] = "SYS_18m.xlsx"
    panels = {p: bfc.load_panel(p, products_map) for p in ["SMT", "SYS"]}
    return panels, legs


@st.cache_data(ttl=600)
def build_series(a: int, b: int):
    panels, legs = load_panels()
    name = f"SSM{a}{b}"
    formula = f"SMT[{a}] - SYS[{b}]"
    scenario = pd.Series({"name": name, "formula": formula,
                          "start_year": 2016, "end_year": 2027,
                          "rolling_window_months": 6, "entry_sd": 2.0})
    df = bfc.build_continuous(panels, scenario, legs)
    if df.empty:
        return name, df
    df["Date"] = pd.to_datetime(df["Date"])
    return name, df


@st.cache_data(ttl=600)
def load_trades(cell_name: str) -> pd.DataFrame:
    fp = SWEEP / cell_name / "trades.xlsx"
    if not fp.exists():
        return pd.DataFrame()
    t = pd.read_excel(fp)
    if t.empty: return t
    t["entry_date"] = pd.to_datetime(t["entry_date"])
    t["exit_date"]  = pd.to_datetime(t["exit_date"])
    t["year"]       = t["entry_date"].dt.year
    return t


def half_life_ar1(x):
    x = np.asarray(x, dtype=float); x = x[~np.isnan(x)]
    if len(x) < 30: return np.nan
    d = np.diff(x); xl = x[:-1]
    xlm, dm = xl.mean(), d.mean()
    num = ((xl-xlm)*(d-dm)).sum(); den = ((xl-xlm)**2).sum()
    if den == 0: return np.nan
    b = num/den
    if b >= 0: return np.inf
    return float(-np.log(2)/b)


def yearly_stats(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty: return pd.DataFrame()
    g = trades.groupby("year").agg(
        n=("pnl", "size"),
        pnl=("pnl", "sum"),
        max_loss=("max_loss", "sum"),
        avg=("pnl", "mean"),
        sd=("pnl", "std"),
        win=("pnl", lambda x: (x > 0).mean() * 100),
        pct_stop=("exit_reason", lambda x: (x == "stop").mean() * 100)
                  if "exit_reason" in trades.columns else ("pnl", lambda x: np.nan),
    )
    g["ratio"] = g["pnl"] / -g["max_loss"]
    g["inv_cv"] = g["avg"] / g["sd"]
    total = pd.DataFrame({
        "n":    [len(trades)],
        "pnl":  [trades["pnl"].sum()],
        "max_loss": [trades["max_loss"].sum()],
        "avg":  [trades["pnl"].mean()],
        "sd":   [trades["pnl"].std()],
        "win":  [(trades["pnl"] > 0).mean() * 100],
        "pct_stop": [(trades["exit_reason"] == "stop").mean() * 100
                       if "exit_reason" in trades.columns else np.nan],
        "ratio": [(trades["pnl"].sum() / -trades["max_loss"].sum())
                    if trades["max_loss"].sum() < 0 else np.nan],
        "inv_cv": [(trades["pnl"].mean() / trades["pnl"].std())
                     if trades["pnl"].std() else np.nan],
    }, index=["TOTAL"])
    return pd.concat([g, total])


# ── Sidebar ──────────────────────────────────────────────────────────
st.sidebar.header("SMT-SYS Outright")
a = st.sidebar.selectbox("SMT offset a (S380)", MONTHS, index=2)   # default 3
b = st.sidebar.selectbox("SYS offset b (S92)",  MONTHS, index=0)   # default 1
window = st.sidebar.selectbox("Rolling window (months)", WINDOWS, index=0)  # 3M
sigma_e = st.sidebar.selectbox("Entry σ", SIGMAS_E, index=1)  # 2.0
sigma_s = st.sidebar.selectbox("Stop σ",  SIGMAS_S, index=0)  # 1.0
slope = st.sidebar.selectbox("Slope filter (BD)", SLOPE_WS, index=0)  # 0 (no filter)

cell_name = f"SSM{a}{b}_W{window}M_SE{sigma_e}_SL{sigma_s}_SLP{slope}"
name, series = build_series(a, b)
trades = load_trades(cell_name)

# ── Header ───────────────────────────────────────────────────────────
st.title("SMT-SYS Outright Viewer")
st.caption(f"**{name}** — `SMT[{a}] − SYS[{b}]`  (S380 fuel oil − S92 gasoline) "
           f"|  blended scaled-roll  |  cell: `{cell_name}`")

if series.empty:
    st.error(f"No series for {name}.")
    st.stop()

# ── Mean-reversion diagnostic ────────────────────────────────────────
design_mask = series["Date"].dt.year.between(2016, 2020)
eval_mask   = series["Date"].dt.year.between(2021, 2026)
hl_d = half_life_ar1(series.loc[design_mask, "EW_adj"].values)
hl_e = half_life_ar1(series.loc[eval_mask,   "EW_adj"].values)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Half-life design (2016-2020)",
            f"{hl_d:.0f} BD" if np.isfinite(hl_d) else "inf",
            help="AR(1) half-life; lower = stronger mean reversion. <60 BD ≈ MR-tradeable.")
col2.metric("Half-life eval (2021-2026)",
            f"{hl_e:.0f} BD" if np.isfinite(hl_e) else "inf")
col3.metric("Trades in cell", f"{len(trades)}")
if not trades.empty:
    col4.metric("Total P&L", f"${trades['pnl'].sum():+.2f}")
    col5.metric("Win rate", f"{(trades['pnl']>0).mean()*100:.0f}%")
else:
    col4.metric("Total P&L", "—")
    col5.metric("Win rate", "—")

# ── Main chart ───────────────────────────────────────────────────────
win_bd = int(window * 22)  # approx
ser = series.set_index("Date")["EW_adj"]
rolling_med = ser.rolling(win_bd, min_periods=win_bd).median()
rolling_std = ser.rolling(win_bd, min_periods=win_bd).std()

upper_e = rolling_med + sigma_e * rolling_std
lower_e = rolling_med - sigma_e * rolling_std
upper_s = rolling_med + sigma_s * rolling_std
lower_s = rolling_med - sigma_s * rolling_std

n_panels = 2 if not trades.empty else 1
fig = make_subplots(
    rows=n_panels, cols=1, shared_xaxes=True,
    row_heights=[0.7, 0.3] if n_panels == 2 else [1.0],
    vertical_spacing=0.04,
    subplot_titles=([f"{name} spread (EW_adj)", "Cumulative P&L"]
                    if n_panels == 2 else [f"{name} spread (EW_adj)"]),
)

# Spread + bands
fig.add_trace(go.Scatter(x=ser.index, y=ser.values, name="EW_adj",
                          line=dict(color="#065DDF", width=1.2)),
              row=1, col=1)
fig.add_trace(go.Scatter(x=rolling_med.index, y=rolling_med.values,
                          name=f"Rolling median ({window}M)",
                          line=dict(color="black", width=1.0, dash="dash")),
              row=1, col=1)
fig.add_trace(go.Scatter(x=upper_e.index, y=upper_e.values,
                          name=f"+{sigma_e}σ entry", line=dict(color="green", width=0.8)),
              row=1, col=1)
fig.add_trace(go.Scatter(x=lower_e.index, y=lower_e.values,
                          name=f"−{sigma_e}σ entry", line=dict(color="green", width=0.8),
                          showlegend=False),
              row=1, col=1)
if sigma_s != sigma_e:
    fig.add_trace(go.Scatter(x=upper_s.index, y=upper_s.values,
                              name=f"+{sigma_s}σ stop", line=dict(color="red", width=0.6, dash="dot")),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=lower_s.index, y=lower_s.values,
                              name=f"−{sigma_s}σ stop", line=dict(color="red", width=0.6, dash="dot"),
                              showlegend=False),
                  row=1, col=1)

# Trade markers
if not trades.empty:
    longs  = trades[trades["side"] == "long"]
    shorts = trades[trades["side"] == "short"]
    if not longs.empty:
        fig.add_trace(go.Scatter(x=longs["entry_date"], y=longs["entry"],
                                  mode="markers", name="Long entry",
                                  marker=dict(symbol="triangle-up", color="green", size=10,
                                              line=dict(color="darkgreen", width=1))),
                      row=1, col=1)
    if not shorts.empty:
        fig.add_trace(go.Scatter(x=shorts["entry_date"], y=shorts["entry"],
                                  mode="markers", name="Short entry",
                                  marker=dict(symbol="triangle-down", color="red", size=10,
                                              line=dict(color="darkred", width=1))),
                      row=1, col=1)
    fig.add_trace(go.Scatter(x=trades["exit_date"], y=trades["exit"],
                              mode="markers", name="Exit",
                              marker=dict(symbol="x", color="gray", size=7)),
                  row=1, col=1)

    # Cumulative P&L
    cum = trades.sort_values("exit_date").reset_index(drop=True)
    cum["cum_pnl"] = cum["pnl"].cumsum()
    fig.add_trace(go.Scatter(x=cum["exit_date"], y=cum["cum_pnl"],
                              name="Cum P&L", line=dict(color="purple", width=1.4),
                              fill="tozeroy", fillcolor="rgba(128,0,128,0.1)"),
                  row=2, col=1)
    fig.add_hline(y=0, line=dict(color="gray", width=0.5), row=2, col=1)

fig.update_xaxes(rangebreaks=RANGEBREAKS)
fig.update_layout(height=750 if n_panels == 2 else 500,
                  hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
st.plotly_chart(fig, use_container_width=True)

# ── Yearly stats ─────────────────────────────────────────────────────
if not trades.empty:
    st.subheader("Yearly P&L breakdown")
    st.dataframe(
        yearly_stats(trades).round(2),
        use_container_width=True,
    )
else:
    st.info(f"No trades generated for cell `{cell_name}`. Try different parameters.")

# ── Performance overview matrix ──────────────────────────────────────
st.subheader(f"All-cells overview for SSM{a}{b}")
overview_rows = []
for w in WINDOWS:
    for se in SIGMAS_E:
        for sl in SIGMAS_S:
            for sw in SLOPE_WS:
                cn = f"SSM{a}{b}_W{w}M_SE{se}_SL{sl}_SLP{sw}"
                t = load_trades(cn)
                if t.empty:
                    overview_rows.append({"W": w, "SE": se, "SL": sl, "SLP": sw,
                                           "n": 0, "pnl": 0.0, "ratio": np.nan,
                                           "win%": np.nan, "longest_uw": np.nan})
                    continue
                ml = t["max_loss"].sum()
                ratio = t["pnl"].sum() / -ml if ml < 0 else np.nan
                overview_rows.append({
                    "W": w, "SE": se, "SL": sl, "SLP": sw,
                    "n": len(t),
                    "pnl": float(t["pnl"].sum()),
                    "ratio": ratio,
                    "win%": (t["pnl"] > 0).mean() * 100,
                    "longest_uw": int(t["bd_underwater"].max()) if "bd_underwater" in t.columns else None,
                })
overview = pd.DataFrame(overview_rows).sort_values("pnl", ascending=False)

def color_pnl(v):
    if pd.isna(v): return ""
    return f"background-color: rgba(0,160,0,{min(abs(v)/30, 0.6):.2f})" if v > 0 \
        else f"background-color: rgba(220,0,0,{min(abs(v)/30, 0.6):.2f})"

st.dataframe(
    overview.style.format({"pnl": "{:+.2f}", "ratio": "{:.2f}",
                            "win%": "{:.0f}%", "longest_uw": "{:.0f}"})
                    .map(color_pnl, subset=["pnl"]),
    use_container_width=True, height=500,
)

st.caption(f"Selected cell highlighted by your sidebar params: `{cell_name}` "
           f"({'in table above' if not overview.empty else 'no data'}).")
