import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

st.set_page_config(layout="wide")

# Paths to the BloombergCOT project (read-only references)
DATA_DIR      = r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\BloombergCOT\data\ice_mifid"
SHOPPING_LIST = r"c:\Users\Jia Shang\OneDrive - Hotei Capital\Desktop\BloombergCOT\shopping_list.xlsx"

CATEGORY_FULL_NAMES = {
    "IF":  "Investment Firms or Credit Institutions",
    "IFu": "Investment Funds",
    "OFI": "Other Financial Institutions",
}
FULL_TO_CODE = {v: k for k, v in CATEGORY_FULL_NAMES.items()}


@st.cache_data(ttl=300)
def load_catalogue() -> pd.DataFrame:
    sl = pd.read_excel(SHOPPING_LIST, sheet_name="shopping_list")
    mask = sl["ice_connect_status"].astype(str).str.startswith("Confirmed", na=False)
    cat = sl[mask][["symbol", "product_name"]].copy()
    cat["symbol"] = cat["symbol"].astype(str)
    cat["product_name"] = cat["product_name"].astype(str)
    cat["label"] = cat["symbol"] + " — " + cat["product_name"]
    cat = cat.sort_values("symbol").reset_index(drop=True)
    return cat


@st.cache_data(ttl=300)
def load_positioning(symbol: str) -> pd.DataFrame:
    fpath = os.path.join(DATA_DIR, f"{symbol}.csv")
    df = pd.read_csv(fpath, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    return df


def aggregate_nc(df: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    long_cols  = [f"{c}_Long_OA_NOPS"  for c in codes]
    short_cols = [f"{c}_Short_OA_NOPS" for c in codes]
    out = pd.DataFrame({"date": df["date"]})
    out["NC_Long"]  = df[long_cols].sum(axis=1)
    out["NC_Short"] = df[short_cols].sum(axis=1)
    out["NC_Net"]   = out["NC_Long"] - out["NC_Short"]
    return out


# ── UI ────────────────────────────────────────────────────────────

st.title("ICE MiFID — Non-Commercial Positioning")
st.caption("OA (Other Activities) commitment, weekly Tuesday-as-of, lots.")

catalogue = load_catalogue()

# --- Sidebar ---
label = st.sidebar.selectbox("Product", options=catalogue["label"].tolist())
symbol = catalogue.loc[catalogue["label"] == label, "symbol"].iloc[0]

selected_full = st.sidebar.multiselect(
    "Non-Commercial categories included",
    options=list(CATEGORY_FULL_NAMES.values()),
    default=list(CATEGORY_FULL_NAMES.values()),
)
selected_codes = [FULL_TO_CODE[n] for n in selected_full]

st.sidebar.markdown("---")
show_long  = st.sidebar.checkbox("Show NC Long line",  value=False)
show_short = st.sidebar.checkbox("Show NC Short line", value=False)

st.sidebar.markdown("---")
show_ma = st.sidebar.checkbox("Overlay moving averages", value=False)
ma_fast = st.sidebar.number_input("Fast MA (weeks)", min_value=1,  max_value=52,  value=2,  step=1)
ma_slow = st.sidebar.number_input("Slow MA (weeks)", min_value=2,  max_value=104, value=12, step=1)

st.sidebar.markdown("---")
show_si     = st.sidebar.checkbox("Show Sentiment Index panel", value=True)
si_lookback = st.sidebar.number_input(
    "SI lookback (weeks)", min_value=8, max_value=260, value=24, step=1,
    help="Rolling window for the SI normalisation. SI = (NC_Net − rolling_min) / (rolling_max − rolling_min)."
)

# --- Load + aggregate ---
df = load_positioning(symbol)

if df.empty:
    st.warning(f"No data for {symbol}.")
    st.stop()

if not selected_codes:
    st.info("Select at least one Non-Commercial category in the sidebar.")
    st.stop()

agg = aggregate_nc(df, selected_codes)

if len(agg) < 2:
    st.warning(f"{symbol} has only {len(agg)} weekly row(s) — too sparse to chart meaningfully.")
    st.dataframe(agg)
    st.stop()

# --- SI series (if requested) ---
si_series = None
if show_si:
    win = int(si_lookback)
    mp  = max(2, win // 3)   # min_periods — need a few obs before SI is meaningful
    nc = agg["NC_Net"]
    rmin = nc.rolling(win, min_periods=mp).min()
    rmax = nc.rolling(win, min_periods=mp).max()
    si_series = (nc - rmin) / (rmax - rmin)

# --- Chart ---
title_str = f"{symbol} — {catalogue.loc[catalogue['symbol']==symbol,'product_name'].iloc[0]}"

if show_si:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.04,
    )
    nc_row, si_row = 1, 2
else:
    fig = make_subplots(rows=1, cols=1)
    nc_row = 1

# NC Net + optional Long / Short
fig.add_trace(go.Scatter(
    x=agg["date"], y=agg["NC_Net"], name="NC Net", mode="lines",
    line=dict(color="black", width=2),
), row=nc_row, col=1)

if show_long:
    fig.add_trace(go.Scatter(
        x=agg["date"], y=agg["NC_Long"], name="NC Long", mode="lines",
        line=dict(color="#2ca02c", width=1.3),
    ), row=nc_row, col=1)
if show_short:
    fig.add_trace(go.Scatter(
        x=agg["date"], y=-agg["NC_Short"], name="NC Short (plotted negative)", mode="lines",
        line=dict(color="#d62728", width=1.3),
    ), row=nc_row, col=1)

if show_ma:
    if ma_slow <= ma_fast:
        st.sidebar.warning("Slow MA must be greater than Fast MA.")
    else:
        ma_f = agg["NC_Net"].rolling(int(ma_fast)).mean()
        ma_s = agg["NC_Net"].rolling(int(ma_slow)).mean()
        fig.add_trace(go.Scatter(
            x=agg["date"], y=ma_f, name=f"MA{int(ma_fast)}w", mode="lines",
            line=dict(color="#1f77b4", width=1.6, dash="dash"),
        ), row=nc_row, col=1)
        fig.add_trace(go.Scatter(
            x=agg["date"], y=ma_s, name=f"MA{int(ma_slow)}w", mode="lines",
            line=dict(color="#ff7f0e", width=1.8, dash="dash"),
        ), row=nc_row, col=1)

fig.add_hline(y=0, line=dict(color="grey", width=1), row=nc_row, col=1)

# SI panel
if show_si:
    fig.add_trace(go.Scatter(
        x=agg["date"], y=si_series, name=f"SI ({int(si_lookback)}w)", mode="lines",
        line=dict(color="#6a3d9a", width=1.6),
    ), row=si_row, col=1)
    fig.add_hline(y=0.95, line=dict(color="#d73027", width=0.8, dash="dot"), row=si_row, col=1)
    fig.add_hline(y=0.50, line=dict(color="grey",   width=0.6),              row=si_row, col=1)
    fig.add_hline(y=0.05, line=dict(color="#1a9850",width=0.8, dash="dot"), row=si_row, col=1)
    fig.update_yaxes(range=[-0.05, 1.05], title_text="SI", row=si_row, col=1)

fig.update_yaxes(title_text="Positioning (lots)", row=nc_row, col=1)
fig.update_xaxes(title_text="Date", row=2 if show_si else 1, col=1)
fig.update_layout(
    template="plotly_white",
    height=780 if show_si else 620,
    margin=dict(l=40, r=20, t=50, b=40),
    title=title_str,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

# --- Footer summary ---
last = agg.iloc[-1]
parts = [
    f"latest {last['date'].date()}",
    f"NC_Net={last['NC_Net']:+,.0f}",
    f"NC_Long={last['NC_Long']:,.0f}",
    f"NC_Short={last['NC_Short']:,.0f}",
    f"weeks={len(agg)}",
    f"included={'+'.join(selected_codes)}",
]
if show_si and si_series is not None and not pd.isna(si_series.iloc[-1]):
    parts.insert(4, f"SI({int(si_lookback)}w)={si_series.iloc[-1]:.3f}")
st.caption("  •  ".join(parts))
